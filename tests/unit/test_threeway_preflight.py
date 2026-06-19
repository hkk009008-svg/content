"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_preflight.py -q"""
import os
import subprocess

import pytest

from threeway.gitcas import preflight_bus_init, BusInitRefusedError


def _env():
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    return env


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True,
                          capture_output=True, text=True, env=_env())


def _new_repo(tmp_path):
    """A repo with one base commit (so HEAD resolves)."""
    r = tmp_path / "repo"; r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@e.st"); _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "base")
    return r


def _new_bare(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    _git(path.parent, "init", "-q", "--bare", str(path))
    return path


def _clone(bare, dest):
    _git(dest.parent, "clone", "-q", str(bare), str(dest))
    _git(dest, "config", "user.email", "t@e.st"); _git(dest, "config", "user.name", "t")
    (dest / "base.txt").write_text("base\n")
    _git(dest, "add", "-A"); _git(dest, "commit", "-qm", "base")
    return dest


def test_preflight_ok_on_empty_repo(tmp_path):
    r = _new_repo(tmp_path)
    preflight_bus_init(r)                                   # no refs/threeway/* -> OK, no raise


def test_preflight_aborts_when_events_ref_exists(tmp_path):
    r = _new_repo(tmp_path)
    head = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", "refs/threeway/events", head)     # stray prior state
    with pytest.raises(BusInitRefusedError):
        preflight_bus_init(r)
    assert _git(r, "rev-parse", "refs/threeway/events").stdout.strip() == head   # NON-DESTRUCTIVE


def test_preflight_checks_remote_refs(tmp_path):
    bare = _new_bare(tmp_path / "bus.git"); r = _clone(bare, tmp_path / "c")
    head = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "push", "origin", f"{head}:refs/threeway/events")   # state on the REMOTE only
    with pytest.raises(BusInitRefusedError):
        preflight_bus_init(r, remote="origin")              # must inspect the remote, not just local


def test_preflight_force_acknowledges_migration(tmp_path):
    r = _new_repo(tmp_path)
    _git(r, "update-ref", "refs/threeway/events", _git(r, "rev-parse", "HEAD").stdout.strip())
    head = _git(r, "rev-parse", "HEAD").stdout.strip()
    preflight_bus_init(r, force=True)                       # explicit migration decision -> proceeds, still no delete
    # force still NEVER deletes prior state
    assert _git(r, "rev-parse", "refs/threeway/events").stdout.strip() == head


def test_preflight_fails_closed_when_remote_unreachable(tmp_path):
    # Real local repo (NO threeway refs) but a bogus remote -> ls-remote exits non-zero.
    # State on the remote is UNDETERMINABLE -> must fail CLOSED, not proceed.
    r = _new_repo(tmp_path)
    bogus = tmp_path / "does-not-exist-remote"               # path that is not a repo
    _git(r, "remote", "add", "origin", str(bogus))
    with pytest.raises(BusInitRefusedError) as exc:
        preflight_bus_init(r, remote="origin")
    # Must be the fail-closed-on-error path, NOT the prior-state path.
    msg = str(exc.value)
    assert "ls-remote" in msg and "fail-closed" in msg
    assert "already exists" not in msg                       # not the prior-state branch


def test_preflight_fails_closed_when_not_a_git_repo(tmp_path):
    # An empty dir that is not a git repo -> for-each-ref exits non-zero ->
    # local enumeration is UNDETERMINABLE -> must fail CLOSED.
    not_a_repo = tmp_path / "not-a-repo"; not_a_repo.mkdir()
    with pytest.raises(BusInitRefusedError) as exc:
        preflight_bus_init(not_a_repo)
    msg = str(exc.value)
    assert "for-each-ref" in msg and "fail-closed" in msg
    assert "already exists" not in msg                       # not the prior-state branch
