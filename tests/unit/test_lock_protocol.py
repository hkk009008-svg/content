# tests/unit/test_lock_protocol.py
import os, subprocess, textwrap
from pathlib import Path
import pytest

BIN = Path(__file__).resolve().parents[2] / "coordination" / "bin"

def _run(cmd, cwd, **kw):
    # UNSET GIT_INDEX_FILE (do not zero it: GIT_INDEX_FILE="" makes `git add` fail
    # rc=128 "unable to write new index file"). CLAUDE.md requires `env -u`.
    env = {k: v for k, v in os.environ.items() if k != "GIT_INDEX_FILE"}
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env, **kw)

def _git(args, cwd):
    r = _run(["git", *args], cwd)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()

@pytest.fixture
def two_clones(tmp_path):
    """A bare 'origin' + two clones (seatA, seatB) sharing it."""
    bare = tmp_path / "origin.git"
    _run(["git", "init", "--bare", str(bare)], tmp_path)
    seatA = tmp_path / "A"; seatB = tmp_path / "B"
    for c, seat in ((seatA, "operator"), (seatB, "operator2")):
        _run(["git", "clone", str(bare), str(c)], tmp_path)
        _git(["config", "user.email", f"{seat}@x"], c)
        _git(["config", "user.name", seat], c)
    # Create coordination/locks ONLY in seatA, commit+push it; seatB receives it via the
    # pull below. Writing .gitkeep into seatB too would make its ff-merge abort on an
    # untracked working-tree file.
    (seatA / "coordination" / "locks").mkdir(parents=True)
    (seatA / "coordination" / "locks" / ".gitkeep").write_text("x\n")
    _git(["add", "-A"], seatA); _git(["commit", "-m", "seed"], seatA)
    _git(["branch", "-M", "main"], seatA)
    _git(["push", "-u", "origin", "main"], seatA)
    # Put seatB on 'main' WITH upstream tracking, deterministically — independent of git's
    # init.defaultBranch. CI runners default to 'master', so a bare clone of the (initially
    # empty) origin leaves seatB on 'master'; `pull --ff-only origin main` would advance
    # 'master' to main's commit but keep seatB ON 'master' with no @{u}. claim-lock then
    # fetches/pushes 'master' (not 'main'), so the lock-collision these tests assert never
    # happens and the second claimant wrongly "wins". checkout -B pins main + @{u}=origin/main.
    _git(["fetch", "origin"], seatB)
    _git(["checkout", "-B", "main", "origin/main"], seatB)
    return seatA, seatB

def test_clean_claim_succeeds_and_pushes(two_clones):
    seatA, _ = two_clones
    r = _run([str(BIN / "claim-lock"), "W1", "core.py", "operator", "bug-1"], seatA)
    assert r.returncode == 0, r.stderr
    assert (seatA / "coordination" / "locks" / "W1-core.py.lock").exists()

def test_second_claimant_aborts_via_precheck(two_clones):
    # PRIMARY defense: claim-lock fetches+ff-merges first, so the 2nd seat SEES the lock
    # file locally and aborts BEFORE committing/pushing. (The push-race is the secondary
    # defense, tested separately below.)
    seatA, seatB = two_clones
    assert _run([str(BIN / "claim-lock"), "W1", "core.py", "operator", "bug-1"], seatA).returncode == 0
    r = _run([str(BIN / "claim-lock"), "W1", "core.py", "operator2", "bug-2"], seatB)
    assert r.returncode != 0, "second claimant must lose via the pre-check"
    # the lock file IS present in seatB now (claim-lock fetch+merged seatA's lock into the
    # worktree); prove seatB never wrote ITS OWN entry — i.e. it did not claim.
    lockf = seatB / "coordination" / "locks" / "W1-core.py.lock"
    assert "operator2" not in lockf.read_text()

def test_release_deletes_and_pushes(two_clones):
    seatA, seatB = two_clones
    # Assert the claim won first — else a silently-failed claim would make the release
    # pass vacuously (release-lock exits 0 when there's no lock to delete).
    assert _run([str(BIN / "claim-lock"), "W1", "core.py", "operator", "bug-1"], seatA).returncode == 0
    assert _run([str(BIN / "release-lock"), "W1", "core.py"], seatA).returncode == 0
    assert not (seatA / "coordination" / "locks" / "W1-core.py.lock").exists()
    _git(["pull", "--ff-only", "origin", "main"], seatB)
    assert not (seatB / "coordination" / "locks" / "W1-core.py.lock").exists()

def test_push_rejection_rollback_primitive(two_clones):
    # SECONDARY defense: a seat that passed its pre-check on a stale view and only loses at
    # push must `git reset --hard origin/main` to drop its dangling local lock commit.
    # We reproduce that exact end-state (origin advanced under a locally-committed lock).
    seatA, seatB = two_clones
    assert _run([str(BIN / "claim-lock"), "W1", "core.py", "operator", "a"], seatA).returncode == 0
    lockB = seatB / "coordination" / "locks" / "W1-core.py.lock"
    lockB.write_text("operator2 W1 t b\n")                # simulate a stale-view local commit
    _git(["add", "--", "coordination/locks/W1-core.py.lock"], seatB)
    _git(["commit", "-m", "racing lock"], seatB)
    assert _run(["git", "push", "origin", "HEAD:main"], seatB).returncode != 0  # non-ff reject
    _git(["fetch", "origin", "main"], seatB)
    _git(["reset", "--hard", "origin/main"], seatB)        # the script's recovery branch
    # The file still EXISTS — the winner's lock lives at this path on origin. What the
    # rollback guarantees is that the LOSER's dangling commit is gone: its content is
    # dropped and replaced by the winner's (same-module race => both seats wrote the same
    # path, so "file gone" is the wrong property; "loser's content gone" is the right one).
    body = lockB.read_text()
    assert "operator2" not in body, "rollback must drop the loser's local lock content"
    assert body.startswith("operator "), "the winner's lock content must be what remains"

def test_lock_filename_flattens_slashes(two_clones):
    # A cross-cutting module with a slash (spec §6b: cinema/context.py) must map to ONE
    # deterministic lock filename, else two seats could 'hold' the same file under
    # different names. Verifies the flat= replacement in claim-lock.
    seatA, _ = two_clones
    assert _run([str(BIN / "claim-lock"), "W1", "cinema/context.py", "operator", "c"], seatA).returncode == 0
    assert (seatA / "coordination" / "locks" / "W1-cinema__context.py.lock").exists()

def test_claim_lock_resets_local_commit_on_push_failure(two_clones):
    # Directly exercises claim-lock's OWN reset branch (the `else` after a failed push,
    # `git reset -q --hard @{u}`) — not just the git primitive. Break the remote so the
    # push fails for real; the script must roll back its local lock commit and exit
    # nonzero, leaving NO dangling lock behind (else a loser would believe it holds it).
    seatA, _ = two_clones
    _git(["remote", "set-url", "origin", "/nonexistent/origin.git"], seatA)
    r = _run([str(BIN / "claim-lock"), "W1", "core.py", "operator", "bug-1"], seatA)
    assert r.returncode != 0, "a failed push must make claim-lock report LOST"
    assert not (seatA / "coordination" / "locks" / "W1-core.py.lock").exists(), \
        "claim-lock must reset its dangling local lock commit on push failure"

def test_release_lock_restores_on_push_failure(two_clones):
    # Symmetric to the above: release-lock must NOT leave a lock looking-released-locally
    # while it is still live on origin. On a failed release-push the script restores the
    # lock locally (`git reset -q --hard @{u}`) and exits nonzero so the caller retries.
    seatA, _ = two_clones
    assert _run([str(BIN / "claim-lock"), "W1", "core.py", "operator", "bug-1"], seatA).returncode == 0
    _git(["remote", "set-url", "origin", "/nonexistent/origin.git"], seatA)
    r = _run([str(BIN / "release-lock"), "W1", "core.py"], seatA)
    assert r.returncode != 0, "a failed release-push must report failure so the caller retries"
    assert (seatA / "coordination" / "locks" / "W1-core.py.lock").exists(), \
        "release-lock must restore the lock locally when the release-push fails"
