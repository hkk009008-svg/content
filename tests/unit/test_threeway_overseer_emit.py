"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_overseer_emit.py -q

overseer_emit CLI scaffold + brief subcommand (threeway scope-b sub-project 1, ADR-056).
The brief subcommand must sign each overseer-authority fact with the OVERSEER key only:
a wrong key makes verify_and_reduce silently DROP the fact (the mutation pin below).
"""
import os
import subprocess
from pathlib import Path

import pytest

from threeway import keys
from threeway.envelope import verify_event
from threeway.gate import verify_and_reduce
from threeway.refstore import RefEventStore


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


def _git(repo, *args):
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    return subprocess.run(["git", "-C", str(repo), *args],
                          check=True, capture_output=True, text=True, env=env)


def _new_repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@e.st")
    _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "base")
    return r


def _events(repo):
    return RefEventStore(Path(repo)).all_events()


def test_brief_round_trips_authority_correct(seatkit, tmp_path):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts.overseer_emit import main
    rc = main(["brief", "--candidate-id", "A:c1", "--brief-id", "b1",
               "--assigned-tier", "T1", "--allowed-paths", "cinema/",
               "--repo-dir", str(repo), "--remote", ""])
    assert rc == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    bf = state.brief("b1", 1)
    assert bf is not None
    assert bf.signer.split(":", 1)[0] == "overseer"
    assert bf.payload["assigned_tier"] == "T1"
    assert bf.payload["allowed_paths"] == ["cinema/"]
    assert "brief_version" not in bf.payload          # envelope-only
    verify_event(bf, keys.PublicKeyRegistry(str(reg)).get("overseer"))  # signature valid


def test_brief_signed_with_nonoverseer_key_is_dropped(seatkit, tmp_path, monkeypatch):
    # MUTATION: if the CLI loaded the wrong seat key, verify_and_reduce drops the fact.
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    # Point load_private("overseer") at the OPERATOR key by overwriting the keystore file.
    (ks / "overseer.ed25519").write_text(keys.private_to_hex(privs["operator"]) + "\n")
    from scripts.overseer_emit import main
    main(["brief", "--candidate-id", "A:c1", "--brief-id", "b1",
          "--assigned-tier", "T1", "--allowed-paths", "cinema/",
          "--repo-dir", str(repo), "--remote", ""])
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    assert state.brief("b1", 1) is None   # signature mismatch vs registry "overseer" pubkey -> dropped


def test_assignment_round_trips(seatkit, tmp_path):
    reg, ks, privs = seatkit; repo = _new_repo(tmp_path)
    from scripts.overseer_emit import main
    assert main(["assignment", "--candidate-id", "A:c1", "--pair", "A",
                 "--builder", "director", "--builder-provider", "codex",
                 "--primary-verifier", "operator", "--primary-verifier-provider", "claude",
                 "--executing-coordinator", "coordinator",
                 "--repo-dir", str(repo), "--remote", ""]) == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    a = state.assignment("A")
    assert a is not None and a.signer.split(":", 1)[0] == "overseer"
    assert a.payload["builder_provider"] == "codex"
    assert a.payload["primary_verifier_provider"] == "claude"
    assert a.payload["executing_coordinator"] == "coordinator"


def test_cycle_go_round_trips(seatkit, tmp_path):
    reg, ks, privs = seatkit; repo = _new_repo(tmp_path)
    from threeway.policy import default_policy
    from scripts.overseer_emit import main
    pd = default_policy().policy_digest()
    assert main(["cycle_go", "--candidate-id", "A:c1", "--brief-id", "b1",
                 "--brief-version", "1", "--tier", "T1", "--policy-digest", pd,
                 "--repo-dir", str(repo), "--remote", ""]) == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    cg = state.cycle_go("b1", 1)
    assert cg is not None and cg.payload["tier"] == "T1" and cg.payload["policy_digest"] == pd


def test_release_order_subject_sha_on_envelope_not_payload(seatkit, tmp_path):
    reg, ks, privs = seatkit; repo = _new_repo(tmp_path)
    from scripts.overseer_emit import main
    assert main(["release_order", "--candidate-id", "A:c1",
                 "--integration-sha", "deadbeef", "--repo-dir", str(repo), "--remote", ""]) == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    ro = state.release_order("A:c1")
    assert ro is not None and ro.signer.split(":", 1)[0] == "overseer"
    assert ro.subject_sha == "deadbeef"          # envelope
    assert ro.payload == {"candidate_id": "A:c1"}  # subject_sha NOT in payload


def test_approver_roster_round_trips(seatkit, tmp_path):
    reg, ks, privs = seatkit; repo = _new_repo(tmp_path)
    from scripts.overseer_emit import main
    assert main(["approver_roster", "--candidate-id", "A:c1",
                 "--approvers", "chief-gemini", "chief-chatgpt",
                 "--repo-dir", str(repo), "--remote", ""]) == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    r = state.approver_roster("A:c1")
    assert r is not None and r.payload["approvers"] == ["chief-gemini", "chief-chatgpt"]


def test_re_verify_challenge_mints_fresh_nonce(seatkit, tmp_path):
    reg, ks, privs = seatkit; repo = _new_repo(tmp_path)
    from scripts.overseer_emit import main
    assert main(["re_verify_challenge", "--candidate-id", "A:c1",
                 "--integration-sha", "deadbeef", "--repo-dir", str(repo), "--remote", ""]) == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    ch = state.re_verify_challenge("A:c1")
    assert ch is not None and ch.subject_sha == "deadbeef"  # envelope
    assert isinstance(ch.payload["nonce"], str) and len(ch.payload["nonce"]) >= 16  # minted
