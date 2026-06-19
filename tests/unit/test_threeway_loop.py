"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_loop.py -q"""
import os
import subprocess

from threeway import keys
from threeway.loop import build_candidate_events, PAIR_A, PAIR_B
from threeway.policy import default_policy
from threeway.refstore import RefEventStore


def _privs_for(seats):
    return {s: keys.generate_keypair()[0] for s in seats}


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


def test_build_candidate_events_has_all_required_kinds():
    privs = {s: keys.generate_keypair()[0] for s in
             ("director", "operator", "coordinator", "overseer", "ci")}
    events = build_candidate_events("1" * 40, "3" * 40, "2" * 40, privs)
    kinds = {e.kind for e in events}
    assert {"brief", "assignment", "candidate", "attestation", "cycle_go",
            "ci_result", "release_requested", "release_order"} <= kinds
    # two attestations: preliminary + release
    atts = [e for e in events if e.kind == "attestation"]
    assert {a.payload["kind"] for a in atts} == {"preliminary", "release"}


def test_build_candidate_events_uses_accepted_policy_digest():
    privs = {s: keys.generate_keypair()[0] for s in
             ("director", "operator", "coordinator", "overseer", "ci")}
    events = build_candidate_events("1" * 40, "3" * 40, "2" * 40, privs)
    pd = default_policy().policy_digest()
    cand = next(e for e in events if e.kind == "candidate")
    assert cand.payload["policy_digest"] == pd


def test_build_candidate_events_for_pair_b():
    privs = _privs_for(("director2", "operator2", "coordinator2", "overseer", "ci"))
    evs = build_candidate_events("1"*40, "3"*40, "2"*40, privs, pair=PAIR_B, candidate_id="c2")
    a = next(e for e in evs if e.kind == "assignment")
    assert a.payload["pair"] == "B"
    assert a.payload["builder"] == "director2" and a.payload["builder_provider"] == "claude"
    assert a.payload["primary_verifier"] == "operator2" and a.payload["primary_verifier_provider"] == "codex"
    assert a.payload["executing_coordinator"] == "coordinator2"
    cand = next(e for e in evs if e.kind == "candidate")
    assert cand.signer.split(":", 1)[0] == "coordinator2"
    assert cand.candidate_id == "c2"


def test_two_pairs_have_disjoint_event_ids_and_per_candidate_release_order():
    privs = _privs_for(("director", "operator", "coordinator", "director2", "operator2",
                        "coordinator2", "overseer", "ci"))
    a = build_candidate_events("1"*40, "3"*40, "2"*40, privs, pair=PAIR_A, candidate_id="c1")
    b = build_candidate_events("1"*40, "4"*40, "5"*40, privs, pair=PAIR_B, candidate_id="c2")
    assert {e.id for e in a}.isdisjoint({e.id for e in b})           # no tree-path collision
    ro_a = next(e for e in a if e.kind == "release_order")
    ro_b = next(e for e in b if e.kind == "release_order")
    assert ro_a.payload["candidate_id"] == "c1" and ro_b.payload["candidate_id"] == "c2"


def test_both_attestations_survive_in_refstore(tmp_path):
    # Regression: the two attestations share kind+sender, so with the default
    # id scheme they collided on RefEventStore's events/<brief_id>/<id>.json path
    # and the release attestation overwrote (LOST) the preliminary one. Distinct,
    # sub-kind-scoped ids must keep BOTH blobs on disk.
    r = _new_repo(tmp_path)
    store = RefEventStore(r)
    privs = _privs_for(("director", "operator", "coordinator", "overseer", "ci"))
    events = build_candidate_events("1" * 40, "3" * 40, "2" * 40, privs,
                                    pair=PAIR_A, candidate_id="c1")
    for ev in events:
        store.append(ev, privs[ev.signer.split(":", 1)[0]])

    atts = [e for e in store.all_events() if e.kind == "attestation"]
    # BOTH sub-kinds present — neither lost to a path collision.
    assert sorted(e.payload["kind"] for e in atts) == ["preliminary", "release"]
    # and the two attestation event ids are distinct.
    assert len({e.id for e in atts}) == 2
