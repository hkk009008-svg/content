"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_overseer_plan.py -q

overseer_plan auto-decompose layer (threeway scope-b automation track, ADR-057).
overseer_plan reads a JSON decision file + the live bus and, on --confirm, emits the overseer facts
emittable now (brief/assignment/cycle_go) by REUSING scripts/overseer_emit (one signing path); it NEVER
emits release_order (DD-4) and surfaces every still-owed non-overseer fact.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

from threeway import keys
from threeway.gate import verify_and_reduce
from threeway.reducer import reduce
from threeway.refstore import RefEventStore


@pytest.fixture()
def seatkit(tmp_path, monkeypatch):
    """Generate keys for every seat; write the public registry + private keystore."""
    reg = tmp_path / "pub"
    ks = tmp_path / "ks"
    reg.mkdir(); ks.mkdir()
    privs = {}
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


def _decision_dict(**over):
    d = {"schema": "overseer-decision/1", "candidate_id": "A:c1", "brief_id": "b1",
         "brief_version": 1, "tier": "T1", "allowed_paths": ["cinema/"],
         "assignment": {"pair": "A", "builder": "director", "builder_provider": "codex",
                        "primary_verifier": "operator", "primary_verifier_provider": "claude",
                        "executing_coordinator": "coordinator"},
         "policy_digest": None}
    d.update(over)
    return d


def _decision_file(tmp_path, **over):
    p = tmp_path / "decision.json"
    p.write_text(json.dumps(_decision_dict(**over)))
    return p


# ── Task 1: decision loader + validation ──────────────────────────────────────

def test_load_decision_valid(tmp_path):
    from scripts.overseer_plan import load_decision
    d = load_decision(str(_decision_file(tmp_path)))
    assert d["candidate_id"] == "A:c1" and d["brief_version"] == 1
    assert d["assignment"]["primary_verifier"] == "operator"


def test_load_decision_missing_field_is_decision_error(tmp_path):
    from scripts.overseer_plan import load_decision, DecisionError
    bad = _decision_dict(); del bad["brief_id"]
    p = tmp_path / "bad.json"; p.write_text(json.dumps(bad))
    with pytest.raises(DecisionError):
        load_decision(str(p))


def test_load_decision_rejects_t3(tmp_path):
    from scripts.overseer_plan import load_decision, DecisionError
    with pytest.raises(DecisionError):
        load_decision(str(_decision_file(tmp_path, tier="T3")))


def test_main_bad_decision_returns_rc2(tmp_path):
    from scripts.overseer_plan import main
    bad = _decision_dict(); del bad["assignment"]
    p = tmp_path / "bad.json"; p.write_text(json.dumps(bad))
    assert main(["--decision", str(p), "--repo-dir", str(_new_repo(tmp_path)), "--remote", ""]) == 2


# ── Task 2: presence planner ──────────────────────────────────────────────────

def test_plan_empty_bus_emits_all_three_and_owes_the_rest(tmp_path):
    from scripts.overseer_plan import load_decision, plan
    d = load_decision(str(_decision_file(tmp_path)))
    emittable, owed = plan(d, reduce([]))
    assert emittable == ["brief", "assignment", "cycle_go"]
    assert ("release_order", "overseer-manual") in owed
    owed_facts = {f for f, _ in owed}
    assert "candidate" in owed_facts and "attestation:preliminary" in owed_facts


def test_plan_idempotent_after_brief_present(seatkit, tmp_path):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts import overseer_emit
    from scripts.overseer_plan import load_decision, plan
    assert overseer_emit.main(["brief", "--candidate-id", "A:c1", "--brief-id", "b1",
                               "--assigned-tier", "T1", "--allowed-paths", "cinema/",
                               "--repo-dir", str(repo), "--remote", ""]) == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    emittable, _ = plan(load_decision(str(_decision_file(tmp_path))), state)
    assert emittable == ["assignment", "cycle_go"]   # brief no longer emittable


# ── Task 3: dry-run (default) + --confirm + Q4 guard ──────────────────────────

def test_dry_run_default_emits_nothing(seatkit, tmp_path, capsys):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts.overseer_plan import main
    rc = main(["--decision", str(_decision_file(tmp_path)), "--repo-dir", str(repo),
               "--registry-dir", str(reg), "--remote", ""])
    assert rc == 0
    assert len(_events(repo)) == 0                       # bus byte-unchanged — nothing signed
    assert "WOULD EMIT" in capsys.readouterr().out


def test_confirm_emits_overseer_facts_never_release_order(seatkit, tmp_path):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts.overseer_plan import main
    rc = main(["--decision", str(_decision_file(tmp_path)), "--repo-dir", str(repo),
               "--registry-dir", str(reg), "--remote", "", "--confirm"])
    assert rc == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    assert state.brief("b1", 1) is not None
    assert state.brief("b1", 1).signer.split(":", 1)[0] == "overseer"
    assert state.assignment("A") is not None
    assert state.cycle_go("b1", 1) is not None
    assert state.release_order("A:c1") is None           # Q4 GUARD: overseer_plan never emits it


# ── Task 4: idempotency ───────────────────────────────────────────────────────

def test_confirm_idempotent_second_run_is_noop(seatkit, tmp_path):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts.overseer_plan import main
    args = ["--decision", str(_decision_file(tmp_path)), "--repo-dir", str(repo),
            "--registry-dir", str(reg), "--remote", "", "--confirm"]
    assert main(args) == 0
    n_after_first = len(_events(repo))
    assert n_after_first == 3                             # brief + assignment + cycle_go
    assert main(args) == 0                                # second run: nothing emittable
    assert len(_events(repo)) == n_after_first            # zero new events; no EventIdCollision failure
