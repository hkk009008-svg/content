"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_bootstrap_emit.py -q"""
import os
import subprocess

import pytest

from threeway import keys
from threeway.gate import verify_and_reduce
from threeway.refstore import RefEventStore


def _env():
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    return env


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


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True,
                          capture_output=True, text=True, env=_env())


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


def test_bootstrap_emit_seat_facts_round_trip(seatkit, live_repo):
    reg, ks, privs = seatkit
    r, base, branch = live_repo                    # fixture: (r, base, branch)
    from scripts.bootstrap_emit import main
    common = ["--candidate-id", "A:c1", "--pair", "A", "--staging-base", base,
              "--branch", branch, "--repo-dir", str(r), "--remote", ""]
    assert main(["candidate", *common]) == 0
    assert main(["attestation", "--phase", "preliminary", *common]) == 0
    assert main(["attestation", "--phase", "release", *common]) == 0
    assert main(["release_requested", *common]) == 0
    state = verify_and_reduce(RefEventStore(r).all_events(),
                              registry_dir=str(reg), bus_id="prod")
    cand = state.candidate("A:c1")
    assert cand is not None and cand.signer.split(":", 1)[0] == "coordinator"
    assert cand.payload["staging_base_sha"] == base and cand.payload["branch_sha"] == branch
    integ = cand.payload["integration_sha"]
    prelim = state.effective_attestation("A:c1", "preliminary", "operator")  # -> Event
    rel = state.effective_attestation("A:c1", "release", "operator")          # -> Event
    assert prelim.payload["verdict"] == "GO" and prelim.subject_sha == branch  # prelim @ branch_sha
    assert rel.payload["verdict"] == "GO" and rel.subject_sha == integ         # release @ integration_sha
    assert state.release_requested("A:c1") is not None    # METHOD — call with the cid


def test_bootstrap_emit_candidate_aborted_is_authoritative(seatkit, live_repo):
    # ADR-060 C1 Part 2: the coordinator-signed candidate_aborted emit lands an abort that the
    # ADR-059 authority gate ACCEPTS — once the overseer assignment binds pair A to "coordinator",
    # is_aborted("A:c1") is True (the CLI always signs with the named pair's coordinator key).
    reg, ks, privs = seatkit
    r, base, branch = live_repo
    from scripts.bootstrap_emit import main as bmain
    from scripts.overseer_emit import main as omain
    otail = ["--repo-dir", str(r), "--remote", "", "--bus-id", "prod"]
    assert omain(["assignment", "--candidate-id", "A:c1", "--pair", "A",
                  "--builder", "director", "--builder-provider", "codex",
                  "--primary-verifier", "operator", "--primary-verifier-provider", "claude",
                  "--executing-coordinator", "coordinator", *otail]) == 0
    assert bmain(["candidate_aborted", "--candidate-id", "A:c1", "--pair", "A",
                  "--brief-id", "b1", "--brief-version", "1",
                  "--repo-dir", str(r), "--remote", ""]) == 0
    state = verify_and_reduce(RefEventStore(r).all_events(),
                              registry_dir=str(reg), bus_id="prod")
    assert state.is_aborted("A:c1")                     # authoritative coordinator abort
    assert "A:c1" in state.aborted_candidate_ids()


def test_bootstrap_emit_candidate_aborted_namespaces_bare_id(seatkit, live_repo):
    # a bare local id is pair-namespaced (consistent with the candidate subcommand) so the abort
    # binds to the same pair-namespaced candidate the gate uses.
    reg, ks, privs = seatkit
    r, base, branch = live_repo
    from scripts.bootstrap_emit import main as bmain
    assert bmain(["candidate_aborted", "--candidate-id", "c9", "--pair", "A",
                  "--brief-id", "b1", "--brief-version", "1",
                  "--repo-dir", str(r), "--remote", ""]) == 0
    state = verify_and_reduce(RefEventStore(r).all_events(),
                              registry_dir=str(reg), bus_id="prod")
    assert "A:c9" in state.aborted_candidate_ids()      # namespaced by pair A


def test_candidate_aborted_bad_repo_dir_exits_clean_rc1(seatkit, tmp_path, capsys):
    # totality: candidate_aborted skips the _candidate_set pre-flight (it references no tree), so a
    # non-git --repo-dir surfaces at the git write. It must return a clean rc 1, not a traceback.
    reg, ks, privs = seatkit
    not_a_repo = tmp_path / "nope"; not_a_repo.mkdir()
    from scripts.bootstrap_emit import main
    rc = main(["candidate_aborted", "--candidate-id", "A:c1", "--pair", "A",
               "--brief-id", "b1", "--brief-version", "1",
               "--repo-dir", str(not_a_repo), "--remote", ""])
    assert rc == 1
    assert "Not emitted" in capsys.readouterr().err


def test_unresolvable_ref_exits_clean_rc1(seatkit, live_repo, capsys):
    # An error path must return rc 1 with a clean message (main honors its -> int contract
    # in-process), NOT raise SystemExit / a traceback.
    reg, ks, privs = seatkit
    r, base, branch = live_repo
    from scripts.bootstrap_emit import main
    rc = main(["candidate", "--candidate-id", "A:c1", "--pair", "A",
               "--staging-base", "no-such-ref", "--branch", branch,
               "--repo-dir", str(r), "--remote", ""])
    assert rc == 1
    assert "Not emitted" in capsys.readouterr().err
