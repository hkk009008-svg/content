"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_e2e_walking_skeleton.py -q

Lives in tests/unit/ (not tests/integration/) because it is fully HERMETIC — temp repo,
temp keys, local subprocesses, no cloud creds — so CI (`pytest tests/unit/`) runs it; the
tests/integration/ dir is reserved for cloud-credential tests excluded from CI.

Task 9: E2E walking-skeleton — T1 brief->merge through the REAL CLIs as subprocesses.
Drives a full T1 candidate brief->merge via overseer_emit / seat_emit /
sign_ci_result / run_merge_gate --run-once against a temp repo + local bus.
Asserts refs/threeway/test-main advances to the recomputed integ and merge_completed
is emitted. [ADR-056]
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from threeway import gitcas, keys
from threeway.gate import verify_and_reduce
from threeway.policy import default_policy
from threeway.refstore import RefEventStore


# ---------------------------------------------------------------------------
# Helpers (copied verbatim from tests/unit/test_threeway_gate.py)
# ---------------------------------------------------------------------------

def _env():
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    return env


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True,
                          capture_output=True, text=True, env=_env())


# ---------------------------------------------------------------------------
# Fixtures (copied from tests/unit/test_threeway_gate.py: seatkit + live_repo + _env/_git)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Subprocess runner
# ---------------------------------------------------------------------------

def _run(script, *args, repo, ks):
    """Invoke a CLI script as a subprocess with the temp keystore env set."""
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    env.pop("PYTHONPATH", None)
    env["THREEWAY_KEYSTORE"] = str(ks)
    proc = subprocess.run(
        [sys.executable, f"scripts/{script}", *args],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, (
        f"{script} {args} failed (rc={proc.returncode}):\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    return proc


# ---------------------------------------------------------------------------
# Walking-skeleton test
# ---------------------------------------------------------------------------

def test_t1_brief_to_merge_walking_skeleton(seatkit, live_repo):
    reg, ks, privs = seatkit
    r, base, branch = live_repo

    cid = "A:c1"
    pd = default_policy().policy_digest()

    # Pre-compute the integration SHA using the same deterministic formula as
    # seat_emit / build_candidate_events so all CLI calls agree on the integ SHA.
    tree, clean = gitcas.merge_tree(r, base, branch)
    assert clean, "live_repo feat branch must merge cleanly against base"
    integ = gitcas.commit_tree(r, tree, [base, branch], f"threeway merge {cid}")

    # Shared flags: repo location + local bus (remote="")
    L = ["--repo-dir", str(r), "--remote", ""]
    # Shared bootstrap flags (staging-base and branch as SHAs so there's no ambiguity)
    B = ["--candidate-id", cid, "--pair", "A",
         "--staging-base", base, "--branch", branch,
         "--repo-dir", str(r), "--remote", ""]

    # 1. Overseer facts ---------------------------------------------------
    _run("overseer_emit.py", "brief",
         "--candidate-id", cid, "--brief-id", "b1",
         "--assigned-tier", "T1", "--allowed-paths", "cinema/",
         *L, repo=r, ks=ks)

    _run("overseer_emit.py", "assignment",
         "--candidate-id", cid,
         "--pair", "A",
         "--builder", "director",
         "--builder-provider", "codex",
         "--primary-verifier", "operator",
         "--primary-verifier-provider", "claude",
         "--executing-coordinator", "coordinator",
         *L, repo=r, ks=ks)

    _run("overseer_emit.py", "cycle_go",
         "--candidate-id", cid, "--brief-id", "b1",
         "--tier", "T1", "--policy-digest", pd,
         *L, repo=r, ks=ks)

    # 2. Interactive-seat facts (candidate + preliminary attestation) ------
    _run("seat_emit.py", "coordinator", "candidate", *B, repo=r, ks=ks)
    _run("seat_emit.py", "operator", "attestation", "--phase", "preliminary", *B, repo=r, ks=ks)

    # 3. CI signer --------------------------------------------------------
    # sign_ci_result defaults --remote to None (local mode) — same local bus as the
    # other CLIs' --remote "" — so it is omitted here intentionally.
    _run("sign_ci_result.py",
         "--integration-sha", integ, "--result", "PASS",
         "--repo-dir", str(r),
         repo=r, ks=ks)

    # 4. Release attestation + release_requested + release_order ----------
    _run("seat_emit.py", "operator", "attestation", "--phase", "release", *B, repo=r, ks=ks)
    _run("seat_emit.py", "coordinator", "release_requested", *B, repo=r, ks=ks)

    _run("overseer_emit.py", "release_order",
         "--candidate-id", cid, "--integration-sha", integ,
         *L, repo=r, ks=ks)

    # 5. Daemon --run-once promotes the TEST ref + emits merge_completed --
    proc = _run("run_merge_gate.py",
                "--repo-dir", str(r),
                "--registry-dir", str(reg),
                "--bus-id", "prod",
                "--main-ref", "refs/threeway/test-main",
                "--run-once",
                repo=r, ks=ks)
    # (daemon stdout/stderr are surfaced in the assertion failure messages below)

    # 6. Assert ref advanced to the integration SHA -----------------------
    actual_head = _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip()
    assert actual_head == integ, (
        f"refs/threeway/test-main did not advance to integ.\n"
        f"Expected: {integ}\n"
        f"Got:      {actual_head}\n"
        f"Daemon stdout:\n{proc.stdout}\nDaemon stderr:\n{proc.stderr}"
    )

    # 7. Assert merge_completed was emitted -------------------------------
    state = verify_and_reduce(
        RefEventStore(r).all_events(),
        registry_dir=str(reg),
        bus_id="prod",
    )
    assert state.merge_completed(cid) is not None, (
        f"merge_completed not found in effective state for {cid!r}.\n"
        f"Daemon stdout:\n{proc.stdout}\nDaemon stderr:\n{proc.stderr}"
    )

    # 8. A real seat reads the whole flow off the bus via consume_bus -----
    proc = _run("consume_bus.py", "coordinator", "--repo-dir", str(r), "--remote", "", repo=r, ks=ks)
    kinds = sorted(line.split("\t")[1] for line in proc.stdout.splitlines() if line.strip())
    assert kinds == sorted([
        "brief", "assignment", "cycle_go", "candidate", "attestation", "attestation",
        "ci_result", "release_requested", "release_order", "merge_completed",
    ])
    n = len(RefEventStore(r).all_events())
    assert RefEventStore(r).cursor_seq("coordinator") == n          # advanced to the snapshot tip
    _run("consume_bus.py", "operator", "--repo-dir", str(r), "--remote", "", repo=r, ks=ks)
    assert RefEventStore(r).cursor_seq("operator") == n             # a second seat also advances


def test_missing_release_attestation_stays_pending(seatkit, live_repo):
    reg, ks, privs = seatkit
    r, base, branch = live_repo
    cid = "A:c1"; pd = default_policy().policy_digest()
    tree, clean = gitcas.merge_tree(r, base, branch)
    integ = gitcas.commit_tree(r, tree, [base, branch], f"threeway merge {cid}")
    L = ["--repo-dir", str(r), "--remote", ""]
    B = ["--candidate-id", cid, "--pair", "A", "--staging-base", base, "--branch", branch, *L]
    _run("overseer_emit.py", "brief", "--candidate-id", cid, "--brief-id", "b1",
         "--assigned-tier", "T1", "--allowed-paths", "cinema/", *L, repo=r, ks=ks)
    _run("overseer_emit.py", "assignment", "--candidate-id", cid, "--pair", "A",
         "--builder", "director", "--builder-provider", "codex",
         "--primary-verifier", "operator", "--primary-verifier-provider", "claude",
         "--executing-coordinator", "coordinator", *L, repo=r, ks=ks)
    _run("overseer_emit.py", "cycle_go", "--candidate-id", cid, "--brief-id", "b1",
         "--tier", "T1", "--policy-digest", pd, *L, repo=r, ks=ks)
    _run("seat_emit.py", "coordinator", "candidate", *B, repo=r, ks=ks)
    _run("seat_emit.py", "operator", "attestation", "--phase", "preliminary", *B, repo=r, ks=ks)
    _run("sign_ci_result.py", "--integration-sha", integ, "--result", "PASS", "--repo-dir", str(r), repo=r, ks=ks)
    # NB: NO release attestation emitted.
    _run("seat_emit.py", "coordinator", "release_requested", *B, repo=r, ks=ks)
    _run("overseer_emit.py", "release_order", "--candidate-id", cid, "--integration-sha", integ, *L, repo=r, ks=ks)
    _run("run_merge_gate.py", "--repo-dir", str(r), "--registry-dir", str(reg),
         "--bus-id", "prod", "--main-ref", "refs/threeway/test-main", "--run-once", repo=r, ks=ks)
    state = verify_and_reduce(RefEventStore(r).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.merge_completed(cid) is None                       # gate PENDING, not COMPLETED
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == base   # ref did NOT advance
