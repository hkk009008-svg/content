"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_gitcas.py -q"""
import os
import subprocess

import pytest

from threeway import gitcas


def _env():
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    return env


def _git(repo, *args, **kw):
    return subprocess.run(["git", "-C", str(repo), *args],
                          check=True, capture_output=True, text=True,
                          env=_env(), **kw)


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@e.st")
    _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "base")
    base = _git(r, "rev-parse", "HEAD").stdout.strip()
    # a branch that adds a NEW file (clean merge with base's later state)
    _git(r, "checkout", "-q", "-b", "feat")
    (r / "feat.txt").write_text("feat\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "feat")
    branch = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "checkout", "-q", "master") if _has(r, "master") else _git(r, "checkout", "-q", "main")
    return r, base, branch


def _has(repo, name):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", name],
                          capture_output=True, env=_env()).returncode == 0


def test_changed_paths(repo):
    r, base, branch = repo
    assert gitcas.changed_paths(r, base, branch) == ["feat.txt"]


def test_merge_tree_clean_returns_tree_and_true(repo):
    r, base, branch = repo
    tree, clean = gitcas.merge_tree(r, base, branch)
    assert clean is True and len(tree) == 40


def test_merge_tree_conflict_returns_false_even_though_git_prints_a_tree(repo):
    r, base, branch = repo
    # create a conflicting branch: edits base.txt differently from a sibling edit
    _git(r, "checkout", "-q", "-b", "conflictA", base)
    (r / "base.txt").write_text("A\n")
    _git(r, "commit", "-aqm", "A")
    a = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "checkout", "-q", "-b", "conflictB", base)
    (r / "base.txt").write_text("B\n")
    _git(r, "commit", "-aqm", "B")
    b = _git(r, "rev-parse", "HEAD").stdout.strip()
    tree, clean = gitcas.merge_tree(r, a, b)
    assert clean is False  # exit-code driven, not "did it print a tree"


def test_commit_tree_is_deterministic(repo):
    r, base, branch = repo
    tree, _ = gitcas.merge_tree(r, base, branch)
    c1 = gitcas.commit_tree(r, tree, [base, branch], "merge")
    c2 = gitcas.commit_tree(r, tree, [base, branch], "merge")
    assert c1 == c2  # fixed author/committer/date => identical OID


def test_cas_update_ref_succeeds_on_matching_old_and_fails_on_stale(repo):
    r, base, branch = repo
    _git(r, "update-ref", "refs/threeway/test-main", base)
    tree, _ = gitcas.merge_tree(r, base, branch)
    merge = gitcas.commit_tree(r, tree, [base, branch], "merge")
    assert gitcas.cas_update_ref(r, "refs/threeway/test-main", merge, base) is True
    # second CAS with the now-stale expected-old must fail
    assert gitcas.cas_update_ref(r, "refs/threeway/test-main", base, base) is False
