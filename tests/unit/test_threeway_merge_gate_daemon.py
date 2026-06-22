"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_merge_gate_daemon.py -q

Daemon-level pins for scripts/run_merge_gate.py (ADR-056 scope-b sub-project 1):
the SAFETY boundary (DD-1: default --main-ref is the protected TEST ref, never
real refs/heads/main), the live-bus --remote (DD-3), and clean SIGTERM/SIGINT
shutdown; plus the run_merge_gate.sh wrapper.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from threeway import gitcas, keys
from threeway.loop import build_candidate_events
from threeway.refstore import RefEventStore
from threeway.gate import verify_and_reduce

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _env():
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    return env


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True,
                          capture_output=True, text=True, env=_env())


@pytest.fixture()
def seatkit(tmp_path, monkeypatch):
    """Generate keys for every seat; write the public registry + private keystore."""
    reg = tmp_path / "pub"
    ks = tmp_path / "ks"
    reg.mkdir(); ks.mkdir()
    privs = {}
    # operator2 = mirror pair-B primary_verifier (T2 co_sign); chief-* = ADR-043 key-bound
    # T3 human approvers (each needs its OWN registry key or its approval is dropped as an
    # unknown signer seat — the operational precondition pinned by the T3 gate tests below).
    for seat in ("director", "operator", "operator2", "coordinator", "overseer", "ci",
                 "merge-gate", "chief-gemini", "chief-chatgpt"):
        priv, pub = keys.generate_keypair()
        (reg / f"{seat}.pub").write_text(pub + "\n")
        (ks / f"{seat}.ed25519").write_text(keys.private_to_hex(priv) + "\n")
        privs[seat] = priv
    monkeypatch.setenv("THREEWAY_KEYSTORE", str(ks))
    return reg, ks, privs


@pytest.fixture()
def live_repo(tmp_path):
    """A repo with a protected test-main ref and a builder branch (clean merge)."""
    r = tmp_path / "repo"; r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@e.st"); _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "base")
    base = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", "refs/threeway/test-main", base)
    _git(r, "checkout", "-q", "-b", "feat")
    (r / "cinema").mkdir()
    (r / "cinema" / "foo.py").write_text("x = 1\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "feat")
    branch = _git(r, "rev-parse", "HEAD").stdout.strip()
    return r, base, branch


def test_default_main_ref_is_test_main_not_real_main():
    # DD-1: a bare invocation must NOT target refs/heads/main.
    from scripts import run_merge_gate
    ns = run_merge_gate._build_argparser().parse_args(["--run-once"])
    assert ns.main_ref == "refs/threeway/test-main"


def test_run_once_merges_a_valid_candidate(seatkit, live_repo):
    reg, ks, privs = seatkit
    r, base, branch = live_repo
    tree, clean = gitcas.merge_tree(r, base, branch); assert clean
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge A:c1")
    store = RefEventStore(r)
    for ev in build_candidate_events(base, branch, integ, {}):   # privs vestigial -> {}
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    from scripts import run_merge_gate
    rc = run_merge_gate.main(["--repo-dir", str(r), "--registry-dir", str(reg),
                              "--bus-id", "prod", "--main-ref", "refs/threeway/test-main",
                              "--run-once"])
    assert rc == 0
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ


def test_stop_flag_exits_clean_without_running_iteration(monkeypatch, capsys):
    # A stop request observed at the top of the loop returns 0, logs the stop line,
    # and does NOT enter poll_once.
    from scripts import run_merge_gate
    monkeypatch.setattr(run_merge_gate, "_STOP", True, raising=False)
    called = {"n": 0}
    monkeypatch.setattr(run_merge_gate, "poll_once",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or [])
    monkeypatch.setattr(run_merge_gate, "load_private", lambda seat: object())
    rc = run_merge_gate.main(["--repo-dir", ".", "--registry-dir", "x", "--bus-id", "prod"])
    assert rc == 0
    assert called["n"] == 0
    assert "merge-gate daemon stopped" in capsys.readouterr().out
