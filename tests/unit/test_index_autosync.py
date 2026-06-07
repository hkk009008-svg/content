"""v5.8 regression tests for _sync_seat_index() in .claude/hooks/update-state.sh.

Mirrors the pattern in test_unread_count.py: slices the REAL function out of
the hook with awk and runs it under bash, so the test guards the production
function, not a copy.

Decision table (from the function's own comment):
  A.  index tree == HEAD tree              -> record marker=HEAD (own commit / already synced)
  B.  HEAD == marker, index diverged       -> deliberate git add since sync — NEVER touch
  C1. HEAD != marker, index == marker tree -> pure peer-commit staleness -> read-tree; marker=HEAD
  C2. HEAD != marker, index != marker tree -> mixed (staged work + peer commit) -> leave for manual read-tree -m
  D.  no marker baseline                   -> converge only via A; never guess

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


def _extract_sync_seat_index() -> str:
    """Slice the real `_sync_seat_index() { … }` body out of the hook with awk."""
    func = subprocess.run(
        ["awk",
         r'/^_sync_seat_index\(\) \{/{p=1} p{print} p&&/^\}/{exit}',
         str(HOOK_PATH)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert func.strip().startswith("_sync_seat_index()") and func.rstrip().endswith("}"), (
        f"failed to extract _sync_seat_index() from {HOOK_PATH}:\n{func!r}"
    )
    return func


def test_extract_sync_seat_index_sanity():
    """Sanity: the awk slice returns a non-empty, well-formed function body."""
    func = _extract_sync_seat_index()
    assert "_sync_seat_index" in func, "extracted text must name the function"
    assert "git read-tree" in func, "extracted function must contain the read-tree call"
    assert "GIT_INDEX_FILE" in func, "extracted function must reference GIT_INDEX_FILE"


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


def _init_repo(tmp: Path) -> dict:
    """
    Init a bare git repo at tmp, create a.txt, commit -> head1.
    Returns clean env (no GIT_INDEX_FILE).
    """
    env = _clean_env()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp, env=env, check=True)
    subprocess.run(["git", "-C", str(tmp), "config", "user.email", "test@test.com"],
                   env=env, check=True)
    subprocess.run(["git", "-C", str(tmp), "config", "user.name", "Test"],
                   env=env, check=True)
    (tmp / "a.txt").write_text("a\n")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp, env=env, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp, env=env, check=True)
    return env


def _head_sha(tmp: Path, env: dict) -> str:
    """Return the full 40-char HEAD sha."""
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp, env=env,
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def _peer_commit(tmp: Path, filename: str, env: dict) -> str:
    """Add filename + commit with DEFAULT index env; return new full HEAD sha."""
    (tmp / filename).write_text(f"{filename}\n")
    subprocess.run(["git", "add", filename], cwd=tmp, env=env, check=True)
    subprocess.run(["git", "commit", "-m", f"peer: add {filename}"],
                   cwd=tmp, env=env, check=True)
    return _head_sha(tmp, env)


def _seed_seat_index(tmp: Path, seat_idx: Path, sha: str):
    """Fast-forward the seat index to the tree at sha via git read-tree."""
    subprocess.run(
        ["git", "read-tree", sha], cwd=tmp, env=_seat_env(seat_idx), check=True,
    )


def _write_marker(marker: Path, sha: str):
    marker.write_text(sha + "\n")


def _marker_dir(tmp: Path) -> Path:
    d = tmp / ".claude" / "hooks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run_sync(tmp: Path, seat_idx: Path, head_sha_arg: str) -> subprocess.CompletedProcess:
    """
    Run _sync_seat_index <head_sha_arg> under bash with cwd=tmp and
    GIT_INDEX_FILE=seat_idx.  The script is built from the REAL extracted
    function — any regression in the hook is caught here.
    """
    func = _extract_sync_seat_index()
    script = (
        "set -euo pipefail\n"
        "export LC_ALL=C\n"
        f'cd "{tmp}"\n'
        f"{func}\n"
        f'_sync_seat_index "{head_sha_arg}"\n'
    )
    return subprocess.run(
        ["bash", "-c", script],
        cwd=tmp,
        env=_seat_env(seat_idx),
        capture_output=True, text=True,
    )


def _index_matches_head(tmp: Path, seat_idx: Path, head: str) -> bool:
    """Return True iff the seat index tree == the tree at head."""
    result = subprocess.run(
        ["git", "diff-index", "--cached", "--quiet", head],
        cwd=tmp, env=_seat_env(seat_idx),
        capture_output=True,
    )
    return result.returncode == 0


def _index_has_file(tmp: Path, seat_idx: Path, filename: str) -> bool:
    """Return True iff filename is staged in the seat index."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", filename],
        cwd=tmp, env=_seat_env(seat_idx),
        capture_output=True, text=True,
    )
    return filename in result.stdout


# ---------------------------------------------------------------------------
# Case C1 — pure peer-commit staleness → read-tree advances index
# ---------------------------------------------------------------------------

def test_c1_pure_staleness_advances_index():
    """
    C1: marker=head1, seat index==head1 tree, peer commits -> head2.
    Run with head2 -> seat index advances to head2 AND marker=head2.
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = _init_repo(tmp)
        head1 = _head_sha(tmp, env)

        seat_idx = tmp / ".git" / "index-operator"
        _seed_seat_index(tmp, seat_idx, head1)

        marker_dir = _marker_dir(tmp)
        marker = marker_dir / ".last-index-sync-index-operator"
        _write_marker(marker, head1)

        head2 = _peer_commit(tmp, "b.txt", env)

        result = _run_sync(tmp, seat_idx, head2)
        assert result.returncode == 0, (
            f"_sync_seat_index exited {result.returncode}; stderr={result.stderr!r}"
        )
        assert _index_matches_head(tmp, seat_idx, head2), (
            "C1: seat index should have advanced to head2 after pure-staleness sync"
        )
        assert marker.read_text().strip() == head2, (
            f"C1: marker should be updated to head2={head2!r}, got {marker.read_text()!r}"
        )


# ---------------------------------------------------------------------------
# Case B — deliberate staged work with HEAD == marker → NEVER touch
# ---------------------------------------------------------------------------

def test_b_staged_work_protected():
    """
    B: marker=head1, stage c.txt into seat index, HEAD still head1.
    Run with head1 -> early return; c.txt still staged; marker unchanged.
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = _init_repo(tmp)
        head1 = _head_sha(tmp, env)

        seat_idx = tmp / ".git" / "index-operator"
        _seed_seat_index(tmp, seat_idx, head1)

        marker_dir = _marker_dir(tmp)
        marker = marker_dir / ".last-index-sync-index-operator"
        _write_marker(marker, head1)

        # Stage c.txt into the SEAT index
        (tmp / "c.txt").write_text("deliberate staged work\n")
        subprocess.run(
            ["git", "add", "c.txt"], cwd=tmp, env=_seat_env(seat_idx), check=True
        )

        result = _run_sync(tmp, seat_idx, head1)
        assert result.returncode == 0, (
            f"_sync_seat_index exited {result.returncode}; stderr={result.stderr!r}"
        )
        assert _index_has_file(tmp, seat_idx, "c.txt"), (
            "B: c.txt should still be staged in seat index (staged-WIP protection)"
        )
        assert marker.read_text().strip() == head1, (
            "B: marker must not advance — no sync occurred"
        )


# ---------------------------------------------------------------------------
# Case C2 — mixed (staged work + peer commit) → leave for manual read-tree -m
# ---------------------------------------------------------------------------

def test_c2_mixed_leaves_index_untouched():
    """
    C2: marker=head1, stage c.txt into seat index, peer commits -> head2.
    Run with head2 -> seat index untouched (c.txt still staged),
    marker still head1 (NOT advanced).
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = _init_repo(tmp)
        head1 = _head_sha(tmp, env)

        seat_idx = tmp / ".git" / "index-operator"
        _seed_seat_index(tmp, seat_idx, head1)

        marker_dir = _marker_dir(tmp)
        marker = marker_dir / ".last-index-sync-index-operator"
        _write_marker(marker, head1)

        # Stage c.txt into the SEAT index
        (tmp / "c.txt").write_text("mixed staged work\n")
        subprocess.run(
            ["git", "add", "c.txt"], cwd=tmp, env=_seat_env(seat_idx), check=True
        )

        # Peer commits b.txt with DEFAULT index
        head2 = _peer_commit(tmp, "b.txt", env)

        result = _run_sync(tmp, seat_idx, head2)
        assert result.returncode == 0, (
            f"_sync_seat_index exited {result.returncode}; stderr={result.stderr!r}"
        )
        # c.txt must still be staged — index was NOT advanced
        assert _index_has_file(tmp, seat_idx, "c.txt"), (
            "C2: c.txt should still be staged (mixed case — manual read-tree -m required)"
        )
        # Verify seat index does NOT match head2 (b.txt would be there if advanced)
        assert not _index_matches_head(tmp, seat_idx, head2), (
            "C2: seat index must NOT have advanced to head2 (staged work present)"
        )
        assert marker.read_text().strip() == head1, (
            "C2: marker must NOT advance — mixed state, no sync"
        )


# ---------------------------------------------------------------------------
# Case A — own-commit / marker catch-up → marker advances, index unchanged
# ---------------------------------------------------------------------------

def test_a_own_commit_marker_catchup():
    """
    A: seat index already at head2 (own commit just landed), marker stale at head1.
    Run with head2 -> marker advances to head2; index byte-identical (no read-tree).
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = _init_repo(tmp)
        head1 = _head_sha(tmp, env)

        seat_idx = tmp / ".git" / "index-operator"
        _seed_seat_index(tmp, seat_idx, head1)

        marker_dir = _marker_dir(tmp)
        marker = marker_dir / ".last-index-sync-index-operator"
        _write_marker(marker, head1)

        # Peer (or own) commit -> head2; manually sync seat index to head2
        head2 = _peer_commit(tmp, "b.txt", env)
        _seed_seat_index(tmp, seat_idx, head2)   # simulate own commit landing

        result = _run_sync(tmp, seat_idx, head2)
        assert result.returncode == 0, (
            f"_sync_seat_index exited {result.returncode}; stderr={result.stderr!r}"
        )
        assert _index_matches_head(tmp, seat_idx, head2), (
            "A: seat index must still match head2 after marker catch-up"
        )
        assert marker.read_text().strip() == head2, (
            f"A: marker should advance to head2={head2!r}, got {marker.read_text()!r}"
        )


# ---------------------------------------------------------------------------
# Case D — no marker baseline → never guess; converge only via A
# ---------------------------------------------------------------------------

def test_d_no_baseline_conservatism():
    """
    D: no marker file, seat index at head1 tree, HEAD=head2.
    Run with head2 -> index unchanged (still head1 tree), no marker created.
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = _init_repo(tmp)
        head1 = _head_sha(tmp, env)

        seat_idx = tmp / ".git" / "index-operator"
        _seed_seat_index(tmp, seat_idx, head1)

        marker_dir = _marker_dir(tmp)
        marker = marker_dir / ".last-index-sync-index-operator"
        # Intentionally do NOT write the marker

        head2 = _peer_commit(tmp, "b.txt", env)

        result = _run_sync(tmp, seat_idx, head2)
        assert result.returncode == 0, (
            f"_sync_seat_index exited {result.returncode}; stderr={result.stderr!r}"
        )
        # Index should still be at head1 (not advanced — no marker baseline)
        assert not _index_matches_head(tmp, seat_idx, head2), (
            "D: seat index must NOT have advanced to head2 — no marker baseline (conservative)"
        )
        assert not marker.exists(), (
            "D: no marker file should be created without a baseline"
        )


# ---------------------------------------------------------------------------
# No GIT_INDEX_FILE → early return, nothing changes
# ---------------------------------------------------------------------------

def test_no_git_index_file_is_noop():
    """
    When GIT_INDEX_FILE is not set, _sync_seat_index returns 0 immediately.
    No marker created, default index untouched.
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = _init_repo(tmp)
        head1 = _head_sha(tmp, env)

        marker_dir = _marker_dir(tmp)
        marker = marker_dir / ".last-index-sync-index-operator"

        func = _extract_sync_seat_index()
        script = (
            "set -euo pipefail\n"
            "export LC_ALL=C\n"
            f'cd "{tmp}"\n'
            f"{func}\n"
            f'_sync_seat_index "{head1}"\n'
        )
        # Run with env that has NO GIT_INDEX_FILE
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=tmp,
            env=_clean_env(),
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"_sync_seat_index (no GIT_INDEX_FILE) exited {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert not marker.exists(), (
            "No GIT_INDEX_FILE: no marker file should be created"
        )
