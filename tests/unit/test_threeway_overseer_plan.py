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
    assert state.assignment("A").signer.split(":", 1)[0] == "overseer"
    assert state.cycle_go("b1", 1) is not None
    assert state.cycle_go("b1", 1).signer.split(":", 1)[0] == "overseer"
    assert state.release_order("A:c1") is None           # Q4 GUARD: overseer_plan never emits it


# ── Task 4: idempotency ───────────────────────────────────────────────────────

def test_confirm_idempotent_second_run_calls_no_emit(seatkit, tmp_path, monkeypatch):
    # NON-VACUOUS: a spy on overseer_emit.main proves the SECOND run early-exits at plan() level
    # (emittable == []) rather than re-emitting and relying on refstore dedup to hide it (the count
    # check alone is vacuous — refstore absorbs duplicate ids regardless of whether plan() early-exits).
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts import overseer_plan
    args = ["--decision", str(_decision_file(tmp_path)), "--repo-dir", str(repo),
            "--registry-dir", str(reg), "--remote", "", "--confirm"]
    assert overseer_plan.main(args) == 0
    n_after_first = len(_events(repo))
    assert n_after_first == 3                             # brief + assignment + cycle_go
    calls = []
    real_main = overseer_plan.overseer_emit.main
    monkeypatch.setattr(overseer_plan.overseer_emit, "main",
                        lambda argv: calls.append(argv[0]) or real_main(argv))
    assert overseer_plan.main(args) == 0                  # second run
    assert calls == []                                   # plan() returned [] -> overseer_emit NOT called
    assert len(_events(repo)) == n_after_first            # and the bus is unchanged


def test_load_decision_rejects_empty_allowed_paths(tmp_path):
    from scripts.overseer_plan import load_decision, DecisionError
    with pytest.raises(DecisionError):
        load_decision(str(_decision_file(tmp_path, allowed_paths=[])))


def test_plan_all_present_emits_nothing(seatkit, tmp_path):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts.overseer_plan import load_decision, main, plan
    args = ["--decision", str(_decision_file(tmp_path)), "--repo-dir", str(repo),
            "--registry-dir", str(reg), "--remote", "", "--confirm"]
    assert main(args) == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    emittable, _ = plan(load_decision(str(_decision_file(tmp_path))), state)
    assert emittable == []                               # all three present -> nothing emittable


def test_confirm_brief_version_2_round_trips_and_is_idempotent(seatkit, tmp_path):
    # Regression for the _emit_argv('brief') brief_version-forwarding bug: a v2 decision must emit
    # brief@v2 (not the argparse v1 default), else plan() never sees it present and re-emits forever.
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts.overseer_plan import main
    args = ["--decision", str(_decision_file(tmp_path, brief_version=2)), "--repo-dir", str(repo),
            "--registry-dir", str(reg), "--remote", "", "--confirm"]
    assert main(args) == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    assert state.brief("b1", 2) is not None               # emitted at v2, not the v1 default (the bug)
    n = len(_events(repo))
    assert main(args) == 0
    assert len(_events(repo)) == n                         # idempotent: plan() sees brief@v2 present


def test_confirm_forwards_bus_id_to_emit(seatkit, tmp_path):
    # DD-5: --bus-id is forwarded to the emit, so the write namespace == the read namespace.
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts.overseer_plan import main
    args = ["--decision", str(_decision_file(tmp_path)), "--repo-dir", str(repo),
            "--registry-dir", str(reg), "--remote", "", "--bus-id", "test", "--confirm"]
    assert main(args) == 0
    briefs = [e for e in _events(repo) if e.kind == "brief"]
    assert briefs and all(e.bus_id == "test" for e in briefs)   # emitted on the 'test' bus namespace


def test_confirm_emit_failure_returns_rc1(seatkit, tmp_path, monkeypatch):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts import overseer_plan
    monkeypatch.setattr(overseer_plan.overseer_emit, "main", lambda argv: 1)  # every emit "fails"
    args = ["--decision", str(_decision_file(tmp_path)), "--repo-dir", str(repo),
            "--registry-dir", str(reg), "--remote", "", "--confirm"]
    assert overseer_plan.main(args) == 1


# ── T3 extension (ADR-058) ────────────────────────────────────────────────────

def _seed_candidate(repo, privs, integ="integ_sha_xyz", tier="T3"):
    """Append a coordinator-signed candidate@A:c1 so plan() sees integration_sha (re_verify_challenge
    becomes emittable). reduce/verify do not validate the SHAs as real git objects."""
    from threeway.loop import build_candidate_events, PAIR_A
    store = RefEventStore(Path(repo))
    for ev in build_candidate_events("base", "branch", integ, {}, tier=tier,
                                     pair=PAIR_A, candidate_id="A:c1"):
        if ev.kind == "candidate":
            store.append(ev, privs["coordinator"])
    return integ


def test_load_decision_accepts_t2_without_approvers(tmp_path):
    from scripts.overseer_plan import load_decision
    assert load_decision(str(_decision_file(tmp_path, tier="T2")))["tier"] == "T2"


def test_load_decision_t3_requires_two_distinct_approvers(tmp_path):
    from scripts.overseer_plan import load_decision, DecisionError
    with pytest.raises(DecisionError):
        load_decision(str(_decision_file(tmp_path, tier="T3")))                          # no approvers
    with pytest.raises(DecisionError):
        load_decision(str(_decision_file(tmp_path, tier="T3", approvers=["only-one"])))  # < 2
    d = load_decision(str(_decision_file(tmp_path, tier="T3",
                                         approvers=["chief-gemini", "chief-chatgpt"])))
    assert d["approvers"] == ["chief-gemini", "chief-chatgpt"]


def test_plan_t3_empty_bus_emits_roster_not_challenge(tmp_path):
    from scripts.overseer_plan import load_decision, plan
    d = load_decision(str(_decision_file(tmp_path, tier="T3",
                                         approvers=["chief-gemini", "chief-chatgpt"])))
    emittable, owed = plan(d, reduce([]))
    assert emittable == ["brief", "assignment", "cycle_go", "approver_roster"]  # no candidate -> no challenge
    owed_facts = {f for f, _ in owed}
    assert {"co_sign", "re_verify", "human_approval"} <= owed_facts


def test_plan_t3_with_candidate_makes_challenge_emittable(seatkit, tmp_path):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    _seed_candidate(repo, privs)
    from scripts.overseer_plan import load_decision, plan
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    d = load_decision(str(_decision_file(tmp_path, tier="T3",
                                         approvers=["chief-gemini", "chief-chatgpt"])))
    emittable, _ = plan(d, state)
    assert "re_verify_challenge" in emittable and "approver_roster" in emittable


def test_confirm_t3_emits_roster_and_challenge_never_release_order(seatkit, tmp_path):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    integ = _seed_candidate(repo, privs)
    from scripts.overseer_plan import main
    dpath = _decision_file(tmp_path, tier="T3", approvers=["chief-gemini", "chief-chatgpt"])
    assert main(["--decision", str(dpath), "--repo-dir", str(repo),
                 "--registry-dir", str(reg), "--remote", "", "--confirm"]) == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    roster = state.approver_roster("A:c1")
    assert roster is not None and roster.signer.split(":", 1)[0] == "overseer"
    assert roster.payload["approvers"] == ["chief-gemini", "chief-chatgpt"]
    ch = state.re_verify_challenge("A:c1")
    assert ch is not None and ch.subject_sha == integ
    assert isinstance(ch.payload["nonce"], str) and len(ch.payload["nonce"]) >= 16  # minted
    assert state.cycle_go("b1", 1).payload["tier"] == "T3"
    assert state.release_order("A:c1") is None           # Q4 GUARD holds at T3 too


def test_confirm_t2_does_not_emit_t3_facts(seatkit, tmp_path):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    _seed_candidate(repo, privs, tier="T2")
    from scripts.overseer_plan import main
    dpath = _decision_file(tmp_path, tier="T2")
    assert main(["--decision", str(dpath), "--repo-dir", str(repo),
                 "--registry-dir", str(reg), "--remote", "", "--confirm"]) == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    assert state.approver_roster("A:c1") is None         # T3-only facts, NOT emitted at T2
    assert state.re_verify_challenge("A:c1") is None
    assert state.cycle_go("b1", 1).payload["tier"] == "T2"


# ── ADR-060 (C1 Part 2): rework-breaker ESCALATE-refusal ──────────────────────

def _append_authorized_reworks(repo, privs, n, *, brief_id="b1", brief_version=1, pair="A",
                               coordinator="coordinator"):
    """Put `n` AUTHORIZED rework cycles on the bus: one overseer assignment + n (candidate, abort)
    pairs signed by the pair's executing_coordinator. Lets should_escalate(state) see real reworks."""
    from threeway.envelope import Event
    store = RefEventStore(Path(repo), remote=None)

    def _ev(kind, sender, signer, cid, payload, eid):
        return Event(id=eid, seq=0, bus_id="prod", schema_version="threeway/1", kind=kind,
                     sender=sender, recipient="all", signer=signer, payload=payload,
                     brief_id=brief_id, brief_version=brief_version, candidate_id=cid)

    store.append(_ev("assignment", "overseer", "overseer:mech:s1", f"{pair}:assign",
                     {"pair": pair, "builder": "director", "builder_provider": "codex",
                      "primary_verifier": "operator", "primary_verifier_provider": "claude",
                      "executing_coordinator": coordinator}, f"assignment-overseer-{pair}"),
                 privs["overseer"])
    csigner = f"{coordinator}:claude:s1"
    for i in range(n):
        cid = f"{pair}:r{i}"
        # distinct payloads per candidate so each fact has a distinct idempotency_key
        # (candidate_id is not in the idempotency fingerprint — envelope.py:105)
        store.append(_ev("candidate", coordinator, csigner, cid,
                         {"pair": pair, "integration_sha": f"integ{i}"},
                         f"candidate-{coordinator}-{cid}"), privs[coordinator])
        store.append(_ev("candidate_aborted", coordinator, csigner, cid, {"candidate_id": cid},
                         f"candidate_aborted-{coordinator}-{cid}"), privs[coordinator])


def test_plan_withholds_cycle_go_on_escalation(tmp_path):
    # ADR-060: when the rework breaker is tripped, plan() withholds a NEW cycle_go (the
    # gate-progressing fact) — fail-safe / requirement-adding direction (ADR-058 DD-1). The other
    # emittable overseer facts are unaffected.
    from scripts.overseer_plan import load_decision, plan
    d = load_decision(str(_decision_file(tmp_path)))
    normal, _ = plan(d, reduce([]))
    assert "cycle_go" in normal                              # baseline: emittable on an empty bus
    escalated, _ = plan(d, reduce([]), escalate=True)
    assert "cycle_go" not in escalated                       # withheld under escalation
    assert "brief" in escalated and "assignment" in escalated


def test_main_escalates_and_withholds_cycle_go_on_repeated_reworks(seatkit, tmp_path, capsys):
    # NON-VACUOUS wiring: main() computes should_escalate from the live bus. With >REWORK_CAP
    # authorized reworks for the decision's brief, it prints ESCALATE and the WOULD EMIT line
    # omits cycle_go (the assignment is already present from the rework setup, so only `brief` remains).
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    _append_authorized_reworks(repo, privs, 3)
    from scripts.overseer_plan import main
    rc = main(["--decision", str(_decision_file(tmp_path)), "--repo-dir", str(repo),
               "--registry-dir", str(reg), "--remote", "none"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ESCALATE" in out
    emit_line = next(l for l in out.splitlines() if "WOULD EMIT" in l)
    assert "cycle_go" not in emit_line and "brief" in emit_line


def test_main_does_not_escalate_below_cap(seatkit, tmp_path, capsys):
    # NON-VACUOUS contrast: exactly REWORK_CAP (2) authorized reworks does NOT escalate, so cycle_go
    # is still offered — proving main() actually evaluates the breaker rather than always-withholding.
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    _append_authorized_reworks(repo, privs, 2)
    from scripts.overseer_plan import main
    rc = main(["--decision", str(_decision_file(tmp_path)), "--repo-dir", str(repo),
               "--registry-dir", str(reg), "--remote", "none"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ESCALATE" not in out
    emit_line = next(l for l in out.splitlines() if "WOULD EMIT" in l)
    assert "cycle_go" in emit_line


def test_main_confirm_does_not_emit_cycle_go_when_escalating(seatkit, tmp_path):
    # NON-VACUOUS: under escalation, --confirm must NOT emit a cycle_go fact onto the bus.
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    _append_authorized_reworks(repo, privs, 3)
    from scripts.overseer_plan import main
    assert main(["--decision", str(_decision_file(tmp_path)), "--repo-dir", str(repo),
                 "--registry-dir", str(reg), "--remote", "none", "--confirm"]) == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    assert state.cycle_go("b1", 1) is None                   # cycle_go WITHHELD by the breaker
    assert state.brief("b1", 1) is not None                  # brief still emitted
