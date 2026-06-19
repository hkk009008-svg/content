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


def _new_repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@e.st")
    _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "base")
    return r        # returns the repo PATH only (not the fixture's tuple)


def _new_bare(path):                       # the authoritative bus remote (spec §8)
    _git(path.parent, "init", "--bare", "-q", str(path))
    return path


def _clone(bare, dest):                    # a seat's working clone of the authority
    _git(dest.parent, "clone", "-q", str(bare), str(dest))
    _git(dest, "config", "user.email", "t@e.st")
    _git(dest, "config", "user.name", "t")
    return dest


def test_write_blob_and_read_back(tmp_path):
    r = _new_repo(tmp_path)
    oid = gitcas.write_blob(r, b'{"k": 1}\n')
    assert len(oid) == 40
    assert gitcas.read_blob(r, oid) == b'{"k": 1}\n'


def test_read_blob_at_commit_path_missing_returns_none(tmp_path):
    r = _new_repo(tmp_path)
    head = _git(r, "rev-parse", "HEAD").stdout.strip()
    assert gitcas.read_blob_at(r, head, "index/00000001") is None


def test_build_tree_extends_parent_and_commits_on_ref(tmp_path):
    r = _new_repo(tmp_path)
    b1 = gitcas.write_blob(r, b'{"e": 1}\n')
    idx1 = gitcas.write_blob(r, b'{"uuid": "e1", "path": "events/b1/e1.json"}\n')
    tree = gitcas.build_tree_with(r, None, [
        ("events/b1/e1.json", b1), ("index/00000001", idx1)])
    c1 = gitcas.commit_on(r, tree, None, "threeway event 00000001")
    assert gitcas.cas_create_or_update_ref(r, "refs/threeway/events", c1, None) is True
    assert gitcas.list_index_seqs(r, c1) == [1]
    assert gitcas.read_blob_at(r, c1, "events/b1/e1.json") == b'{"e": 1}\n'


def test_cas_create_rejects_when_ref_already_exists(tmp_path):
    r = _new_repo(tmp_path)
    tree = gitcas.build_tree_with(r, None, [("index/00000001", gitcas.write_blob(r, b"x"))])
    c1 = gitcas.commit_on(r, tree, None, "e1")
    assert gitcas.cas_create_or_update_ref(r, "refs/threeway/events", c1, None) is True
    assert gitcas.cas_create_or_update_ref(r, "refs/threeway/events", c1, None) is False  # ref exists


def test_second_event_extends_first_tree(tmp_path):
    r = _new_repo(tmp_path)
    t1 = gitcas.build_tree_with(r, None, [("index/00000001", gitcas.write_blob(r, b"a"))])
    c1 = gitcas.commit_on(r, t1, None, "e1")
    t1_tree = _git(r, "rev-parse", f"{c1}^{{tree}}").stdout.strip()
    t2 = gitcas.build_tree_with(r, t1_tree, [("index/00000002", gitcas.write_blob(r, b"b"))])
    c2 = gitcas.commit_on(r, t2, c1, "e2")
    assert gitcas.list_index_seqs(r, c2) == [1, 2]


def test_tree_of_resolves_commit_tree(tmp_path):
    r = _new_repo(tmp_path)
    c1 = gitcas.commit_on(r, gitcas.build_tree_with(
        r, None, [("index/00000001", gitcas.write_blob(r, b"a"))]), None, "e1")
    assert gitcas.tree_of(r, c1) == _git(r, "rev-parse", f"{c1}^{{tree}}").stdout.strip()
    assert gitcas.tree_of(r, "0" * 39 + "1") is None      # unresolvable -> None


def test_list_index_seqs_empty_when_ref_absent(tmp_path):
    r = _new_repo(tmp_path)
    assert gitcas.list_index_seqs(r, "refs/threeway/nope") == []


def test_build_tree_with_leaves_no_scratch_index(tmp_path):
    r = _new_repo(tmp_path)
    gitcas.build_tree_with(r, None, [("index/00000001", gitcas.write_blob(r, b"a"))])
    assert list(r.glob("*.idx")) == []


def test_push_cas_create_update_and_lease_mismatch(tmp_path):
    bare = _new_bare(tmp_path / "bus.git")
    seat = _clone(bare, tmp_path / "seat")
    other = _clone(bare, tmp_path / "other")
    ref = "refs/threeway/events"
    # create on empty remote ref succeeds
    c1 = gitcas.commit_on(seat, gitcas.build_tree_with(
        seat, None, [("index/00000001", gitcas.write_blob(seat, b"a"))]), None, "e1")
    assert gitcas.push_cas(seat, "origin", c1, ref, None) is True
    # a second create (expected_old=None) must fail — the ref now exists
    c1b = gitcas.commit_on(seat, gitcas.build_tree_with(
        seat, None, [("index/00000001", gitcas.write_blob(seat, b"a2"))]), None, "e1b")
    assert gitcas.push_cas(seat, "origin", c1b, ref, None) is False
    # update with the correct expected_old succeeds
    t1_tree = gitcas.tree_of(seat, c1)
    c2 = gitcas.commit_on(seat, gitcas.build_tree_with(
        seat, t1_tree, [("index/00000002", gitcas.write_blob(seat, b"b"))]), c1, "e2")
    assert gitcas.push_cas(seat, "origin", c2, ref, c1) is True
    # a stale expected_old (the seat thinks the tip is still c1) loses the lease -> False
    c3 = gitcas.commit_on(other, gitcas.build_tree_with(
        other, None, [("index/00000003", gitcas.write_blob(other, b"c"))]), None, "e3")
    assert gitcas.push_cas(other, "origin", c3, ref, c1) is False


def test_push_cas_create_rejects_existing_ref_even_if_fast_forward(tmp_path):
    """create-only (expected_old=None) must reject an EXISTING remote ref even when the
    pushed commit is a fast-forward descendant of the tip. A plain `push commit:ref`
    git accepts as a FF, silently violating create-only; the zero-OID lease catches it."""
    bare = _new_bare(tmp_path / "bus.git")
    seat = _clone(bare, tmp_path / "seat")
    ref = "refs/threeway/events"
    # establish a tip on the remote ref
    c1 = gitcas.commit_on(seat, gitcas.build_tree_with(
        seat, None, [("index/00000001", gitcas.write_blob(seat, b"a"))]), None, "e1")
    assert gitcas.push_cas(seat, "origin", c1, ref, None) is True
    # a FAST-FORWARD descendant of c1 (parent=c1, extends its tree) — a plain push would FF-accept
    t1_tree = gitcas.tree_of(seat, c1)
    c2 = gitcas.commit_on(seat, gitcas.build_tree_with(
        seat, t1_tree, [("index/00000002", gitcas.write_blob(seat, b"b"))]), c1, "e2")
    # create-form push of the FF descendant must be REJECTED (the ref already exists)
    assert gitcas.push_cas(seat, "origin", c2, ref, None) is False


def test_fetch_ref_returns_remote_tip_or_none(tmp_path):
    bare = _new_bare(tmp_path / "bus.git")
    seat = _clone(bare, tmp_path / "seat")
    other = _clone(bare, tmp_path / "other")
    ref = "refs/threeway/events"
    assert gitcas.fetch_ref(other, "origin", ref) is None  # remote ref does not exist yet
    c1 = gitcas.commit_on(seat, gitcas.build_tree_with(
        seat, None, [("index/00000001", gitcas.write_blob(seat, b"a"))]), None, "e1")
    assert gitcas.push_cas(seat, "origin", c1, ref, None) is True
    assert gitcas.fetch_ref(other, "origin", ref) == c1


def test_for_each_ref_lists_local_threeway_refs(tmp_path):
    r = _new_repo(tmp_path)
    c1 = gitcas.commit_on(r, gitcas.build_tree_with(
        r, None, [("index/00000001", gitcas.write_blob(r, b"a"))]), None, "e1")
    assert gitcas.cas_create_or_update_ref(r, "refs/threeway/events", c1, None) is True
    assert gitcas.for_each_ref(r, "refs/threeway/*") == ["refs/threeway/events"]


def test_ls_remote_refs_lists_remote_threeway_refs(tmp_path):
    bare = _new_bare(tmp_path / "bus.git")
    seat = _clone(bare, tmp_path / "seat")
    other = _clone(bare, tmp_path / "other")
    ref = "refs/threeway/events"
    assert gitcas.ls_remote_refs(other, "origin", "refs/threeway/*") == []
    c1 = gitcas.commit_on(seat, gitcas.build_tree_with(
        seat, None, [("index/00000001", gitcas.write_blob(seat, b"a"))]), None, "e1")
    assert gitcas.push_cas(seat, "origin", c1, ref, None) is True
    assert gitcas.ls_remote_refs(other, "origin", "refs/threeway/*") == [ref]


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
