"""Regression tests for _clear_skip_worktree() in .claude/hooks/update-state.sh.

Workflow/subagent harness runs have twice polluted the active git index with
skip-worktree bits (N=4 earlier sessions; N=767 observed 2026-06-10), which
hides the seat's own edits from `git status` and breaks `git add`/`git rm`
with phantom "outside of your sparse-checkout definition" errors even though
no sparse checkout is configured. No legitimate skip-worktree use exists in
this repo, so any flagged entry is pollution; the hook clears the flag bit
per-path (`git update-index --no-skip-worktree`), which never touches staged
content — unlike `git read-tree HEAD`, the manual wholesale fix.

Mirrors the pattern in test_index_autosync.py: slices the REAL function out
of the hook with awk and runs it under bash, so the test guards the
production function, not a copy.

TRAP (documented in memory da_git_index_file_breaks_pytest_temp_repos):
  The outer dev session exports GIT_INDEX_FILE pointing at the REAL repo's
  per-seat index.  ALL git subprocess calls in this test must use an env
  constructed from os.environ.copy() with GIT_INDEX_FILE either POPPED
  (for default-index operations on the temp repo) or SET to the seat index
  path (for seat-index operations).  Leaking the outer env causes git to
  write/read the wrong index and produces false failures.
"""
import os
import subprocess
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Extract the production function from the hook (NOT a copy)
# ---------------------------------------------------------------------------

HOOK_PATH = Path(__file__).parents[2] / ".claude" / "hooks" / "update-state.sh"


def _extract_clear_skip_worktree() -> str:
    """Slice the real `_clear_skip_worktree() { … }` body out of the hook with awk."""
    func = subprocess.run(
        ["awk",
         r'/^_clear_skip_worktree\(\) \{/{p=1} p{print} p&&/^\}/{exit}',
         str(HOOK_PATH)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert func.strip().startswith("_clear_skip_worktree()") and func.rstrip().endswith("}"), (
        f"failed to extract _clear_skip_worktree() from {HOOK_PATH}:\n{func!r}"
    )
    return func


def test_extract_clear_skip_worktree_sanity():
    """Sanity: the awk slice returns a non-empty, well-formed function body."""
    func = _extract_clear_skip_worktree()
    assert "_clear_skip_worktree" in func, "extracted text must name the function"
    assert "--no-skip-worktree" in func, (
        "extracted function must contain the per-path flag clear "
        "(content-preserving; NOT read-tree)"
    )


def test_hook_calls_clear_before_skip_perf_gate():
    """Wiring guard: the hook must CALL the function (a defined-but-never-called
    function is invisible to the slice-based tests), and the call must come
    BEFORE the skip-perf early exit — pollution lands WITHOUT a HEAD move, so a
    call after the gate would be skipped exactly when it is needed."""
    text = HOOK_PATH.read_text()
    call_pos = text.find("_clear_skip_worktree ")
    # the gate is the only `"$CURRENT" = "$LAST"` comparison in the hook
    gate_pos = text.find('"$CURRENT" = "$LAST"')
    assert call_pos != -1, "hook must call _clear_skip_worktree"
    assert gate_pos != -1, "skip-perf gate not found (hook restructured? update test)"
    assert call_pos < gate_pos, (
        "_clear_skip_worktree must be called BEFORE the skip-perf gate: "
        "skip-worktree pollution arrives without a HEAD move"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_env() -> dict:
    """Return os.environ with GIT_INDEX_FILE removed (safe for default-index ops)."""
    env = os.environ.copy()
    env.pop("GIT_INDEX_FILE", None)
    return env


def _seat_env(seat_idx: Path) -> dict:
    """Return env with GIT_INDEX_FILE pointing at the seat index."""
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = str(seat_idx)
    return env


def _init_repo(tmp: Path, filenames=("a.txt", "b.txt", "c.txt")) -> dict:
    """Init a repo at tmp, commit filenames. Returns clean env (no GIT_INDEX_FILE)."""
    env = _clean_env()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp, env=env, check=True)
    subprocess.run(["git", "-C", str(tmp), "config", "user.email", "test@test.com"],
                   env=env, check=True)
    subprocess.run(["git", "-C", str(tmp), "config", "user.name", "Test"],
                   env=env, check=True)
    for name in filenames:
        (tmp / name).write_text(f"{name}\n")
    subprocess.run(["git", "add", "--", *filenames], cwd=tmp, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp, env=env, check=True)
    return env


def _seed_seat_index(tmp: Path, seat_idx: Path, env: dict):
    """Create the seat index as a copy of HEAD's tree via git read-tree."""
    subprocess.run(["git", "read-tree", "HEAD"], cwd=tmp,
                   env=_seat_env(seat_idx), check=True)


def _set_skip_worktree(tmp: Path, env: dict, *paths: str):
    """Flag paths skip-worktree in whatever index env resolves (simulated pollution)."""
    subprocess.run(["git", "update-index", "--skip-worktree", "--", *paths],
                   cwd=tmp, env=env, check=True)


def _flagged_paths(tmp: Path, env: dict) -> list:
    """Return the list of skip-worktree-flagged paths in env's index."""
    out = subprocess.run(["git", "ls-files", "-v"], cwd=tmp, env=env,
                         capture_output=True, text=True, check=True).stdout
    return [line[2:] for line in out.splitlines() if line.startswith("S ")]


def _run_clear(tmp: Path, env: dict) -> subprocess.CompletedProcess:
    """Run _clear_skip_worktree under bash with cwd=tmp and the given env.

    Built from the REAL extracted function — any hook regression is caught here.
    `set -euo pipefail` matches the hook's own options.
    """
    func = _extract_clear_skip_worktree()
    script = (
        "set -euo pipefail\n"
        "export LC_ALL=C\n"
        f'cd "{tmp}"\n'
        f"{func}\n"
        "_clear_skip_worktree\n"
    )
    return subprocess.run(["bash", "-c", script], cwd=tmp, env=env,
                          capture_output=True, text=True)


def _staged_content(tmp: Path, env: dict, path: str) -> str:
    """Return the staged blob content of path in env's index."""
    return subprocess.run(["git", "cat-file", "blob", f":{path}"], cwd=tmp, env=env,
                          capture_output=True, text=True, check=True).stdout


# ---------------------------------------------------------------------------
# Core behavior — flagged entries get cleared, nothing else changes
# ---------------------------------------------------------------------------

def test_clears_skip_worktree_bits_on_seat_index():
    """Pollution on the seat index (the production case: the child process
    inherited GIT_INDEX_FILE) is cleared; all entries remain cached."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = _init_repo(tmp)
        seat_idx = tmp / ".git" / "index-operator"
        _seed_seat_index(tmp, seat_idx, env)
        seat = _seat_env(seat_idx)

        _set_skip_worktree(tmp, seat, "a.txt", "b.txt")
        assert _flagged_paths(tmp, seat) == ["a.txt", "b.txt"], "pollution seeding failed"

        result = _run_clear(tmp, seat)
        assert result.returncode == 0, (
            f"_clear_skip_worktree exited {result.returncode}; stderr={result.stderr!r}"
        )
        assert _flagged_paths(tmp, seat) == [], "flags must be cleared"
        cached = subprocess.run(["git", "ls-files", "--cached"], cwd=tmp, env=seat,
                                capture_output=True, text=True, check=True).stdout.split()
        assert cached == ["a.txt", "b.txt", "c.txt"], (
            "clearing the flag must not evict entries from the index"
        )


def test_preserves_staged_content():
    """The flag clear is content-preserving: deliberate staged work survives —
    the property that makes this safe to run unconditionally, where the
    wholesale `git read-tree HEAD` fix would destroy staged work."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = _init_repo(tmp)
        seat_idx = tmp / ".git" / "index-operator"
        _seed_seat_index(tmp, seat_idx, env)
        seat = _seat_env(seat_idx)

        (tmp / "staged.txt").write_text("deliberate staged work\n")
        subprocess.run(["git", "add", "staged.txt"], cwd=tmp, env=seat, check=True)
        _set_skip_worktree(tmp, seat, "a.txt")

        result = _run_clear(tmp, seat)
        assert result.returncode == 0, (
            f"_clear_skip_worktree exited {result.returncode}; stderr={result.stderr!r}"
        )
        assert _flagged_paths(tmp, seat) == [], "flag must be cleared"
        assert _staged_content(tmp, seat, "staged.txt") == "deliberate staged work\n", (
            "staged content must survive the clear byte-for-byte"
        )


def test_noop_when_clean():
    """No flagged entries -> exit 0, no log entry (the common case must stay
    silent and cheap: this runs on every PostToolUse Bash/Write/Edit)."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = _init_repo(tmp)
        seat_idx = tmp / ".git" / "index-operator"
        _seed_seat_index(tmp, seat_idx, env)
        seat = _seat_env(seat_idx)
        (tmp / ".claude" / "hooks").mkdir(parents=True)

        result = _run_clear(tmp, seat)
        assert result.returncode == 0, (
            f"_clear_skip_worktree exited {result.returncode}; stderr={result.stderr!r}"
        )
        assert not (tmp / ".claude" / "hooks" / ".skip-worktree-cleared.log").exists(), (
            "no-op runs must not write the log"
        )


def test_clears_on_default_index_without_git_index_file():
    """Unlike _sync_seat_index, the clear is NOT gated on GIT_INDEX_FILE: a
    session running on the default index gets polluted there, and the flag
    clear is equally safe on any index."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = _init_repo(tmp)
        _set_skip_worktree(tmp, env, "b.txt")
        assert _flagged_paths(tmp, env) == ["b.txt"], "pollution seeding failed"

        result = _run_clear(tmp, env)
        assert result.returncode == 0, (
            f"_clear_skip_worktree exited {result.returncode}; stderr={result.stderr!r}"
        )
        assert _flagged_paths(tmp, env) == [], "default-index flags must be cleared too"


def test_clears_path_with_space():
    """Paths with spaces must round-trip the ls-files -> update-index handoff
    (NUL-delimited plumbing, not word-splitting)."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = _init_repo(tmp, filenames=("a.txt", "with space.txt"))
        _set_skip_worktree(tmp, env, "with space.txt")
        assert _flagged_paths(tmp, env) == ["with space.txt"], "pollution seeding failed"

        result = _run_clear(tmp, env)
        assert result.returncode == 0, (
            f"_clear_skip_worktree exited {result.returncode}; stderr={result.stderr!r}"
        )
        assert _flagged_paths(tmp, env) == [], "space-containing path must be cleared"


def test_logs_clear_event():
    """A clearing run appends one line with the cleared count — the evidence
    trail for root-causing the (so-far unreproduced) polluting operation."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = _init_repo(tmp)
        seat_idx = tmp / ".git" / "index-operator"
        _seed_seat_index(tmp, seat_idx, env)
        seat = _seat_env(seat_idx)
        (tmp / ".claude" / "hooks").mkdir(parents=True)

        _set_skip_worktree(tmp, seat, "a.txt", "b.txt", "c.txt")
        result = _run_clear(tmp, seat)
        assert result.returncode == 0, (
            f"_clear_skip_worktree exited {result.returncode}; stderr={result.stderr!r}"
        )
        log = tmp / ".claude" / "hooks" / ".skip-worktree-cleared.log"
        assert log.exists(), "a clearing run must append to the log"
        assert "cleared=3" in log.read_text(), (
            f"log must record the cleared count, got: {log.read_text()!r}"
        )
