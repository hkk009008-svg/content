"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_seat_emit.py -q"""
import contextlib
import io
import os
import subprocess

import pytest

from threeway import keys
from threeway.gate import verify_and_reduce
from threeway.refstore import RefEventStore


# --- fixtures copied from tests/unit/test_threeway_gate.py (per-file convention) ---
def _env():
    env = dict(os.environ); env.pop("GIT_INDEX_FILE", None); return env


def _git(repo, *a, stdin=None):
    return subprocess.run(["git", "-C", str(repo), *a], check=True,
                          capture_output=True, text=(stdin is None), input=stdin, env=_env())


@pytest.fixture()
def seatkit(tmp_path, monkeypatch):
    reg = tmp_path / "pub"; ks = tmp_path / "ks"; reg.mkdir(); ks.mkdir()
    for seat in ("director", "director2", "operator", "operator2", "coordinator", "coordinator2",
                 "overseer", "ci", "merge-gate"):
        priv, pub = keys.generate_keypair()
        (reg / f"{seat}.pub").write_text(pub + "\n")
        (ks / f"{seat}.ed25519").write_text(keys.private_to_hex(priv) + "\n")
    monkeypatch.setenv("THREEWAY_KEYSTORE", str(ks))
    return reg, ks


@pytest.fixture()
def live_repo(tmp_path):
    r = tmp_path / "repo"; r.mkdir()
    _git(r, "init", "-q"); _git(r, "config", "user.email", "t@e.st"); _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n"); _git(r, "add", "-A"); _git(r, "commit", "-qm", "base")
    base = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", "refs/threeway/test-main", base)
    _git(r, "checkout", "-q", "-b", "feat")
    (r / "cinema").mkdir(); (r / "cinema" / "f.py").write_text("x = 1\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "feat")
    branch = _git(r, "rev-parse", "HEAD").stdout.strip()
    return r, base, branch


def _run(argv):
    from scripts.seat_emit import main
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


def test_operator_attestation_round_trips_and_verifies(seatkit, live_repo):
    reg, ks = seatkit
    r, base, branch = live_repo
    common = ["--candidate-id", "c1", "--pair", "A", "--staging-base", base, "--branch", branch,
              "--repo-dir", str(r), "--remote", ""]
    assert _run(["operator", "attestation", "--phase", "preliminary", *common])[0] == 0
    state = verify_and_reduce(RefEventStore(r).all_events(), registry_dir=str(reg), bus_id="prod")
    att = state.effective_attestation("A:c1", "preliminary", "operator")   # folded + sig-verified by the gate
    assert att is not None and att.payload["verdict"] == "GO" and att.subject_sha == branch


def test_authority_bypass_is_rc2_and_zero_new_events(seatkit, live_repo):
    reg, ks = seatkit
    r, base, branch = live_repo
    n0 = len(RefEventStore(r).all_events())
    rc, _, err = _run(["director", "attestation", "--phase", "preliminary", "--candidate-id", "c1",
                       "--pair", "A", "--staging-base", base, "--branch", branch,
                       "--repo-dir", str(r), "--remote", ""])
    assert rc == 2 and "may not emit" in err                               # static seat↔kind guard fires
    assert len(RefEventStore(r).all_events()) == n0                        # NOTHING appended (non-vacuous)


def test_release_requested_bypass_is_rc2_zero_events(seatkit, live_repo):
    # class-(3): the gate never reads release_requested; only seat_emit's guard matters.
    reg, ks = seatkit
    r, base, branch = live_repo
    n0 = len(RefEventStore(r).all_events())
    rc, _, _ = _run(["director", "release_requested", "--candidate-id", "c1", "--pair", "A",
                     "--staging-base", base, "--branch", branch, "--repo-dir", str(r), "--remote", ""])
    assert rc == 2 and len(RefEventStore(r).all_events()) == n0


def test_candidate_aborted_authoritative_fold(seatkit, live_repo):
    # MIGRATED from test_bootstrap_emit_candidate_aborted_is_authoritative
    reg, ks = seatkit
    r, base, branch = live_repo
    from scripts.overseer_emit import main as omain
    otail = ["--repo-dir", str(r), "--remote", "", "--bus-id", "prod"]
    assert omain(["assignment", "--candidate-id", "A:c1", "--pair", "A",
                  "--builder", "director", "--builder-provider", "codex",
                  "--primary-verifier", "operator", "--primary-verifier-provider", "claude",
                  "--executing-coordinator", "coordinator", *otail]) == 0
    assert _run(["coordinator", "candidate_aborted", "--candidate-id", "c1", "--pair", "A",
                 "--repo-dir", str(r), "--remote", ""])[0] == 0
    state = verify_and_reduce(RefEventStore(r).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.is_aborted("A:c1") is True


def test_candidate_aborted_namespaces_bare_id(seatkit, live_repo):
    # MIGRATED from test_bootstrap_emit_candidate_aborted_namespaces_bare_id
    reg, ks = seatkit
    r, *_ = live_repo
    _run(["coordinator", "candidate_aborted", "--candidate-id", "c9", "--pair", "A",
          "--repo-dir", str(r), "--remote", ""])
    aborts = [e for e in RefEventStore(r).all_events() if e.kind == "candidate_aborted"]
    assert aborts and aborts[-1].candidate_id == "A:c9"


def test_candidate_aborted_bad_repo_dir_exits_clean_rc1(seatkit, tmp_path):
    # MIGRATED error-path totality: a non-git repo-dir -> clean rc1, no traceback
    reg, ks = seatkit
    nope = tmp_path / "nope"; nope.mkdir()
    rc, _, err = _run(["coordinator", "candidate_aborted", "--candidate-id", "c1", "--pair", "A",
                       "--repo-dir", str(nope), "--remote", ""])
    assert rc == 1 and "Not emitted" in err


def test_unresolvable_ref_exits_clean_rc1(seatkit, live_repo):
    # MIGRATED error-path totality (candidate path): bad staging-base ref -> clean rc1
    reg, ks = seatkit
    r, base, branch = live_repo
    rc, _, err = _run(["coordinator", "candidate", "--candidate-id", "c1", "--pair", "A",
                       "--staging-base", "no-such-ref", "--branch", branch,
                       "--repo-dir", str(r), "--remote", ""])
    assert rc == 1 and "Not emitted" in err


def test_tier_sets_risk_tier_claimed(seatkit, live_repo):
    reg, ks = seatkit
    r, base, branch = live_repo
    _run(["coordinator", "candidate", "--candidate-id", "c1", "--pair", "A", "--tier", "T2",
          "--staging-base", base, "--branch", branch, "--repo-dir", str(r), "--remote", ""])
    cand = [e for e in RefEventStore(r).all_events() if e.kind == "candidate"][-1]
    assert cand.payload["risk_tier_claimed"] == "T2"


def test_coordinator2_candidate_round_trips_pair_b(seatkit, live_repo):
    # PAIR_B emission coverage (requires coordinator2 in the extended seatkit).
    reg, ks = seatkit
    r, base, branch = live_repo
    assert _run(["coordinator2", "candidate", "--candidate-id", "c1", "--pair", "B",
                 "--staging-base", base, "--branch", branch, "--repo-dir", str(r), "--remote", ""])[0] == 0
    state = verify_and_reduce(RefEventStore(r).all_events(), registry_dir=str(reg), bus_id="prod")
    cand = state.candidate("B:c1")
    assert cand is not None and cand.signer.split(":", 1)[0] == "coordinator2"
