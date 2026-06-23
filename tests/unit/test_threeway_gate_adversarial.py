"""The spec §11 Slice 1 gate. Each test mutates ONE fact in an otherwise-valid
promotion and asserts the gate does NOT advance refs/threeway/test-main.

Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_gate_adversarial.py -q
"""
import os
import subprocess

import pytest

from threeway import gitcas, keys
from threeway.gate import run_gate, GateError, verify_and_reduce
from threeway.loop import build_candidate_events
from threeway.store import EventStore


def _env():
    env = dict(os.environ); env.pop("GIT_INDEX_FILE", None); return env


def _git(r, *a):
    return subprocess.run(["git", "-C", str(r), *a], check=True,
                          capture_output=True, text=True, env=_env())


@pytest.fixture()
def world(tmp_path, monkeypatch):
    # keys
    reg = tmp_path / "pub"; ks = tmp_path / "ks"; reg.mkdir(); ks.mkdir()
    privs = {}
    for seat in ("director", "operator", "coordinator", "overseer", "ci", "merge-gate"):
        priv, pub = keys.generate_keypair()
        (reg / f"{seat}.pub").write_text(pub + "\n")
        (ks / f"{seat}.ed25519").write_text(keys.private_to_hex(priv) + "\n")
        privs[seat] = priv
    monkeypatch.setenv("THREEWAY_KEYSTORE", str(ks))
    # repo
    r = tmp_path / "repo"; r.mkdir()
    _git(r, "init", "-q"); _git(r, "config", "user.email", "t@e.st"); _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n"); _git(r, "add", "-A"); _git(r, "commit", "-qm", "base")
    base = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", "refs/threeway/test-main", base)
    _git(r, "checkout", "-q", "-b", "feat")
    (r / "cinema").mkdir(); (r / "cinema" / "foo.py").write_text("x = 1\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "feat")
    branch = _git(r, "rev-parse", "HEAD").stdout.strip()
    tree, _ = gitcas.merge_tree(r, base, branch)
    # IMPORTANT: stage with the SAME message the gate recomputes with, so the
    # exact-SHA equality check passes for the clean-merge cases.
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge A:c1")
    return r, base, branch, integ, reg, ks, privs


def _populate(store, events, privs):
    for ev in events:
        store.append(ev, privs[ev.signer.split(":", 1)[0]])


def _head(r):
    return _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip()


def _run(world, mutate=None, bus_id="prod"):
    r, base, branch, integ, reg, ks, privs = world
    store = EventStore(r / "coordination" / "threeway" / "events")
    events = build_candidate_events(base, branch, integ, privs, bus_id=bus_id)
    if mutate:
        mutate(events)
    _populate(store, events, privs)
    return r, base, store, reg, privs


def test_clean_change_merges(world):
    r, base, store, reg, privs = _run(world)
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "COMPLETED"
    assert _head(r) != base  # advanced


# ---- the adversarial rejections (§11 Slice 1 gate) ----

def test_rejects_tampered_integration_sha(world):
    def mut(events):
        for e in events:
            if e.kind == "candidate":
                e.payload["integration_sha"] = "d" * 40  # not the real merge
    r, base, store, reg, privs = _run(world, mut)
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "REJECTED"
    assert _head(r) == base  # NOT advanced


def test_drops_absent_signature(world):
    # ADR-040: a load-bearing event with NO signature is DROPPED, not raised — one unsigned event
    # must not brick run_gate for every candidate. Here the unsigned event is a candidate_aborted
    # for c1: had it verified it would ABORT the merge, but being unsigned it has zero authority and
    # is dropped, so the legit promotion still COMPLETES. (Fail-safe: dropping only removes the
    # forged abort; it can never admit a forged fact or block a legit merge.)
    r, base, branch, integ, reg, ks, privs = world
    store = EventStore(r / "coordination" / "threeway" / "events")
    events = build_candidate_events(base, branch, integ, privs)
    _populate(store, events, privs)
    # hand-write an unsigned candidate_aborted into the store dir
    from threeway.envelope import Event, to_json_obj
    import json
    bad = Event(id="bad", seq=999, bus_id="prod", schema_version="threeway/1",
                kind="candidate_aborted", sender="coordinator", recipient="all",
                signer="coordinator:claude:s1", payload={}, candidate_id="A:c1")
    p = r / "coordination" / "threeway" / "events" / "00000999-bad.json"
    p.write_text(json.dumps(to_json_obj(bad)))  # no signature
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "COMPLETED", res.reason   # did NOT raise; unsigned abort dropped
    assert _head(r) == integ                          # legit merge proceeded


def test_rejects_valid_signature_wrong_seat(world):
    # operator signs a release_order that only the overseer may sign. With record-time
    # authority filtering (ADR-039) the wrong-seat release_order is IGNORED entirely —
    # a strictly stronger §11 realization than read-time rejection: the forged fact has
    # zero effect on effective state, so the candidate is non-promotable (PENDING,
    # awaiting a legit overseer release_order). The merge MUST NOT happen (main == base).
    def mut(events):
        for e in events:
            if e.kind == "release_order":
                e.signer = "operator:claude:s1"  # wrong seat for this fact
    r, base, branch, integ, reg, ks, privs = world
    store = EventStore(r / "coordination" / "threeway" / "events")
    events = build_candidate_events(base, branch, integ, privs)
    mut(events)
    # sign release_order with the operator key so the SIGNATURE verifies (operator is a
    # registered seat) — but the record-time filter DROPS it from effective state because
    # release_order is an overseer-only authority, so state.release_order("c1") is None.
    for ev in events:
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "PENDING" and "release_order" in res.reason
    assert _head(r) == base


def test_rejects_old_go_then_fail(world):
    from threeway.envelope import Event
    def mut(events):
        events.append(Event(id="latefail", seq=0, bus_id="prod",
                            schema_version="threeway/1", kind="attestation",
                            sender="operator", recipient="all",
                            signer="operator:claude:s1",
                            payload={"kind": "release", "verdict": "FAIL"},
                            subject_sha=events[2].payload["integration_sha"],
                            candidate_id="A:c1", brief_id="b1", brief_version=1))
    r, base, store, reg, privs = _run(world, mut)
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "PENDING"
    assert _head(r) == base


def test_rejects_candidate_modifying_ci_workflow(world):
    # the diff includes a CI workflow file -> path-derived T2 > cycle_go T1 -> escalation
    r, base, branch, integ, reg, ks, privs = world
    # add a workflow change to the feat branch and re-stage
    _git(r, "checkout", "-q", "feat")
    (r / ".github" / "workflows").mkdir(parents=True)
    (r / ".github" / "workflows" / "ci.yml").write_text("name: x\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "weaken ci")
    branch2 = _git(r, "rev-parse", "HEAD").stdout.strip()
    tree, _ = gitcas.merge_tree(r, base, branch2)
    integ2 = gitcas.commit_tree(r, tree, [base, branch2], "stage c1")
    store = EventStore(r / "coordination" / "threeway" / "events")
    events = build_candidate_events(base, branch2, integ2, privs,
                                    allowed_paths=("cinema/", ".github/"))
    _populate(store, events, privs)
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "REJECTED" and "tier_escalation" in res.reason
    assert _head(r) == base


def test_rejects_stage_ref_moved_after_attestation(world):
    r, base, store, reg, privs = _run(world)
    # main moves before the gate runs
    _git(r, "commit", "--allow-empty", "-qm", "drift")
    drift = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", "refs/threeway/test-main", drift)
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "REJECTED" and "stale" in res.reason
    assert _head(r) == drift  # untouched


def test_rejects_tier_mislabeled_below_minimum(world):
    def mut(events):
        for e in events:
            if e.kind == "candidate":
                e.payload["risk_tier_claimed"] = "T0"  # lie; gate recomputes
    # diff is just cinema/foo.py (T1) so claim-lowering alone doesn't escalate;
    # pair it with a CI path to prove the gate uses the path minimum, not the claim
    r, base, branch, integ, reg, ks, privs = world
    _git(r, "checkout", "-q", "feat")
    (r / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (r / ".github" / "workflows" / "ci.yml").write_text("name: y\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "ci")
    b2 = _git(r, "rev-parse", "HEAD").stdout.strip()
    tree, _ = gitcas.merge_tree(r, base, b2)
    i2 = gitcas.commit_tree(r, tree, [base, b2], "stage")
    store = EventStore(r / "coordination" / "threeway" / "events")
    events = build_candidate_events(base, b2, i2, privs, tier="T0",
                                    allowed_paths=("cinema/", ".github/"))
    _populate(store, events, privs)
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "REJECTED" and "tier_escalation" in res.reason
    assert _head(r) == base


def test_rejects_diff_outside_allowed_paths(world):
    r, base, branch, integ, reg, ks, privs = world
    store = EventStore(r / "coordination" / "threeway" / "events")
    # allowed_paths excludes cinema/, but the diff is cinema/foo.py
    events = build_candidate_events(base, branch, integ, privs, allowed_paths=("docs/",))
    _populate(store, events, privs)
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "REJECTED" and "allowed_paths" in res.reason
    assert _head(r) == base


def test_drops_replay_from_test_bus(world):
    # ADR-040: the whole promotion is replayed from the WRONG bus (TEST-BUS while the gate runs
    # 'prod'). Every load-bearing event is DROPPED at the bus_id check, not raised — so NO candidate
    # fact survives in effective state and the gate returns PENDING ("no candidate fact yet"),
    # never advancing main. (Dropping a wrong-bus replay can only REMOVE events; it never promotes.)
    r, base, store, reg, privs = _run(world, bus_id="TEST-BUS")
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "PENDING" and "no candidate" in res.reason   # all events dropped; did NOT raise
    assert _head(r) == base   # main untouched (fail-closed)


def test_crash_after_release_before_cas_recovers_without_double_write(world):
    # run twice; the CAS expected-old + merge_completed make the 2nd a no-op
    r, base, store, reg, privs = _run(world)
    a = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                 main_ref="refs/threeway/test-main")
    head_after_first = _head(r)
    b = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                 main_ref="refs/threeway/test-main")
    assert a.outcome == "COMPLETED" and b.outcome == "COMPLETED"
    assert _head(r) == head_after_first  # no second write
    completes = [e for e in store.all_events() if e.kind == "merge_completed"]
    assert len(completes) == 1


def test_one_rework_cycle_completes_then_third_escalates(world):
    # ADR-060: should_escalate counts only AUTHORIZED reworks over REDUCED state, through the real
    # signed store + verify_and_reduce. Three pair-A candidates of brief b1/v1, each aborted by the
    # pair's executing_coordinator -> escalate only on the third (> REWORK_CAP).
    from threeway.envelope import Event
    from threeway.rework import should_escalate
    r, base, branch, integ, reg, ks, privs = world
    store = EventStore(r / "coordination" / "threeway" / "events")
    # one overseer assignment binds pair A to executing_coordinator "coordinator"
    assignment = next(e for e in build_candidate_events(base, branch, integ, privs)
                      if e.kind == "assignment")
    store.append(assignment, privs["overseer"])

    def candidate(cid):
        return Event(id=f"candidate-coordinator-{cid}", seq=0, bus_id="prod",
                     schema_version="threeway/1", kind="candidate", sender="coordinator",
                     recipient="all", signer="coordinator:claude:s1", payload={"pair": "A"},
                     brief_id="b1", brief_version=1, candidate_id=cid)

    def abort(cid):
        # payload={} is safe HERE because this test uses EventStore (Slice-1, store.py), which has
        # NO idempotency dedup. The live RefEventStore DOES dedup by idempotency_key (payload_digest
        # included, candidate_id NOT), so the production abort emit carries payload={"candidate_id": cid}
        # to disambiguate (bootstrap_emit._abort_event).
        return Event(id=f"candidate_aborted-coordinator-{cid}", seq=0, bus_id="prod",
                     schema_version="threeway/1", kind="candidate_aborted", sender="coordinator",
                     recipient="all", signer="coordinator:claude:s1", payload={},
                     brief_id="b1", brief_version=1, candidate_id=cid)

    def escalates():
        state = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
        return should_escalate(state, "b1", 1)

    for cid in ("A:c1", "A:c2"):
        store.append(candidate(cid), privs["coordinator"])
        store.append(abort(cid), privs["coordinator"])
    assert not escalates()
    store.append(candidate("A:c3"), privs["coordinator"])
    store.append(abort("A:c3"), privs["coordinator"])
    assert escalates()
