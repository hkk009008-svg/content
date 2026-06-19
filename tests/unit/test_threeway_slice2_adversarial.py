"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_slice2_adversarial.py -q

Spec §11 Slice 2 (second gate): two candidates from two pairs target main; the single
mechanical gate (sole writer) promotes ONE via exact-SHA CAS, the other's staging_base
!= main.head so the gate REJECTs it "stale" WITHOUT writing, and rework re-stages it as
a NEW candidate (new candidate_id, staging_base = the advanced main.head, branch rebased
onto main) -> COMPLETED.

Slice 1 already implements the CAS + the "stale" REJECTED (predicate freshness check +
the CAS expected-old precondition). This file proves the two-candidate SERIAL behavior +
the re-stage path across Pair A and Pair B. Inline harness (no shared conftest).
"""
import os
import subprocess

import pytest

from threeway import gitcas, keys
from threeway.envelope import idempotency_key
from threeway.refstore import RefEventStore
from threeway.gate import run_gate
from threeway.loop import build_candidate_events, PAIR_A, PAIR_B

MAIN = "refs/threeway/test-main"
_SEATS = ("director", "operator", "coordinator", "director2", "operator2",
          "coordinator2", "overseer", "ci", "merge-gate")

# allowed_paths: the predicate's _within_allowed/_under (predicate.py) uses a path-
# SEGMENT boundary — "cinema" matches "cinema/..." but a TOP-LEVEL file matches only via
# == (no "./" handling; (".",) would NOT match a.txt). The world's diffs are the top-
# level files a.txt / b.txt, so the brief must allow BOTH by exact name. Both candidates
# share ONE brief (build_candidate_events hardcodes brief_id="b1"); the reducer keys the
# brief by (brief_id, version), so the two pairs MUST carry an identical allowed_paths or
# the second brief would OVERWRITE the first in reduced state. One brief authorizing the
# path-set {a.txt, b.txt} is the faithful single-fact model; each candidate's own diff
# still falls inside it.
_ALLOW = ("a.txt", "b.txt")


# _env / _git copied verbatim from test_threeway_gate_adversarial.py
def _env():
    env = dict(os.environ); env.pop("GIT_INDEX_FILE", None); return env


def _git(r, *a):
    return subprocess.run(["git", "-C", str(r), *a], check=True,
                          capture_output=True, text=True, env=_env())


def _head(r):
    return _git(r, "rev-parse", MAIN).stdout.strip()


def _populate(store, events, privs, _seen=None):
    # The RefEventStore dedups on idempotency_key (sender:kind:subject_sha:payload_digest).
    # The overseer-signed brief-level facts (brief, cycle_go) are candidate-INDEPENDENT,
    # so a second candidate of the SAME brief re-emits a byte-identical-keyed event. The
    # bus holds ONE copy of each logical fact — appending the second copy would raise
    # IdempotencyKeyReused (its _request_fingerprint differs only in candidate_id). Skip
    # any key already on the bus to model "one shared fact, appended once" — exactly the
    # bus's own dedup contract. Per-candidate facts (candidate, the candidate-bound
    # attestations, ci_result, release_order) carry a distinct subject_sha/payload, so
    # they have distinct keys and always land. `_seen` is threaded across calls so a later
    # candidate sees the earlier candidate's already-landed shared facts.
    seen = _seen if _seen is not None else set()
    for ev in events:
        k = idempotency_key(ev)
        if k in seen:
            continue
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
        seen.add(k)
    return seen


def _stage(r, base, branch, cid):
    # The gate recomputes the merge with message f"threeway merge {cid}" under the
    # deterministic env and REJECTs unless it equals the attested integration_sha.
    # _stage MUST use the IDENTICAL message + env so the gate's recomputed SHA matches.
    tree, clean = gitcas.merge_tree(r, base, branch)
    assert clean
    return gitcas.commit_tree(r, tree, [base, branch], f"threeway merge {cid}")


@pytest.fixture()
def world_two_pairs(tmp_path, monkeypatch):
    r = tmp_path / "repo"; r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@e.st"); _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n"); _git(r, "add", "-A"); _git(r, "commit", "-qm", "base")
    base = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", MAIN, base)
    _git(r, "checkout", "-q", "-b", "feat_a")
    (r / "a.txt").write_text("a\n"); _git(r, "add", "-A"); _git(r, "commit", "-qm", "a")
    branch_a = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "checkout", "-q", base); _git(r, "checkout", "-q", "-b", "feat_b")
    (r / "b.txt").write_text("b\n"); _git(r, "add", "-A"); _git(r, "commit", "-qm", "b")
    branch_b = _git(r, "rev-parse", "HEAD").stdout.strip()
    reg = tmp_path / "pub"; ks = tmp_path / "ks"; reg.mkdir(); ks.mkdir(); privs = {}
    for s in _SEATS:
        priv, pub = keys.generate_keypair()
        (reg / f"{s}.pub").write_text(pub + "\n")
        (ks / f"{s}.ed25519").write_text(keys.private_to_hex(priv) + "\n")
        privs[s] = priv
    monkeypatch.setenv("THREEWAY_KEYSTORE", str(ks))
    return r, base, branch_a, branch_b, reg, privs


@pytest.fixture()
def world_conflict(tmp_path, monkeypatch):
    # Two branches that BOTH modify the same shared.txt off the same base -> they
    # 3-way-conflict. Pair A lands clean (only branch_a touched shared.txt vs base);
    # Pair B, re-targeted FRESH onto the advanced main, then conflicts on shared.txt.
    r = tmp_path / "repo"; r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@e.st"); _git(r, "config", "user.name", "t")
    (r / "shared.txt").write_text("L0\n"); _git(r, "add", "-A"); _git(r, "commit", "-qm", "base")
    base = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", MAIN, base)
    _git(r, "checkout", "-q", "-b", "feat_a")
    (r / "shared.txt").write_text("A\n"); _git(r, "add", "-A"); _git(r, "commit", "-qm", "a")
    branch_a = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "checkout", "-q", base); _git(r, "checkout", "-q", "-b", "feat_b")
    (r / "shared.txt").write_text("B\n"); _git(r, "add", "-A"); _git(r, "commit", "-qm", "b")
    branch_b = _git(r, "rev-parse", "HEAD").stdout.strip()
    reg = tmp_path / "pub"; ks = tmp_path / "ks"; reg.mkdir(); ks.mkdir(); privs = {}
    for s in _SEATS:
        priv, pub = keys.generate_keypair()
        (reg / f"{s}.pub").write_text(pub + "\n")
        (ks / f"{s}.ed25519").write_text(keys.private_to_hex(priv) + "\n")
        privs[s] = priv
    monkeypatch.setenv("THREEWAY_KEYSTORE", str(ks))
    return r, base, branch_a, branch_b, reg, privs


# Both candidates share ONE brief (build_candidate_events hardcodes brief_id="b1"; the
# reducer keys the brief by (brief_id, version)), so they MUST carry an identical
# allowed_paths or the second brief OVERWRITES the first in reduced state. Both diffs
# are the single top-level file shared.txt -> allow it by exact name (the predicate's
# _under uses a path-SEGMENT boundary; a top-level file matches only via ==).
_ALLOW_SHARED = ("shared.txt",)


def test_conflicting_candidate_aborts_with_merge_not_clean(world_conflict):
    # The §11 abort-on-conflict -> rework path across two pairs. Pair A's c1 lands clean
    # and advances main. Pair B's c2 is FRESH onto the new main (staging_base == main.head,
    # so it PASSES the predicate's freshness check -> NOT the "stale" reject of Task 14),
    # but its branch genuinely CONFLICTS with main on shared.txt. The gate recomputes the
    # merge ITSELF and, finding it unclean, REJECTs "merge not clean ... -> ABORT/REWORK"
    # BEFORE comparing the attested integration_sha -- with the protected ref UNMOVED.
    r, base, branch_a, branch_b, reg, privs = world_conflict
    store = RefEventStore(r)

    # 1. Pair A's c1 lands cleanly (merge(base, branch_a) is clean -- only branch_a moved
    #    shared.txt vs base). main advances to a_integ (shared.txt="A").
    a_integ = _stage(r, base, branch_a, "c1")
    seen = _populate(store, build_candidate_events(base, branch_a, a_integ, privs,
                                                   pair=PAIR_A, candidate_id="c1",
                                                   allowed_paths=_ALLOW_SHARED), privs)
    r1 = run_gate("c1", store, r, registry_dir=reg, bus_id="prod", main_ref=MAIN)
    assert r1.outcome == "COMPLETED", r1.reason
    new_main = _head(r); assert new_main == a_integ

    # 2. Pair B's c2 is FRESH onto the advanced main (staging_base = a_integ == main.head)
    #    but its branch CONFLICTS. _stage CANNOT build this candidate -- it asserts the
    #    merge is clean. So fabricate a REAL integration_sha (branch_b, a real commit): the
    #    gate rejects "merge not clean" BEFORE it ever compares the attested SHA, so the
    #    exact value only needs to be real (predicate F2 guard) -- not the true merge.
    #    Sanity: the diff stays inside the shared brief's allowed_paths {shared.txt}.
    assert set(gitcas.changed_paths(r, a_integ, branch_b)) <= {"shared.txt"}
    _populate(store, build_candidate_events(a_integ, branch_b, branch_b, privs,
                                            pair=PAIR_B, candidate_id="c2",
                                            allowed_paths=_ALLOW_SHARED), privs, seen)

    # 3. The gate aborts on the conflict and leaves the protected ref unmoved.
    r2 = run_gate("c2", store, r, registry_dir=reg, bus_id="prod", main_ref=MAIN)
    assert r2.outcome == "REJECTED", r2.reason
    # the reason proves freshness PASSED and the CONFLICT (not staleness) aborted it:
    assert "merge not clean" in r2.reason, r2.reason
    assert "stale" not in r2.reason, r2.reason
    assert _head(r) == a_integ            # protected ref UNMOVED on the conflicting candidate


def test_serial_queue_rejects_stale_loser_then_restage_completes(world_two_pairs):
    r, base, branch_a, branch_b, reg, privs = world_two_pairs
    store = RefEventStore(r)
    # Both candidates stage onto the SAME base — they race for the one main slot.
    a_integ = _stage(r, base, branch_a, "c1")
    b_integ = _stage(r, base, branch_b, "c2")
    seen = _populate(store, build_candidate_events(base, branch_a, a_integ, privs,
                                                   pair=PAIR_A, candidate_id="c1",
                                                   allowed_paths=_ALLOW), privs)
    _populate(store, build_candidate_events(base, branch_b, b_integ, privs,
                                            pair=PAIR_B, candidate_id="c2",
                                            allowed_paths=_ALLOW), privs, seen)

    # Pair A's c1 wins the slot: the gate promotes it via exact-SHA CAS, main -> a_integ.
    r1 = run_gate("c1", store, r, registry_dir=reg, bus_id="prod", main_ref=MAIN)
    assert r1.outcome == "COMPLETED", r1.reason
    new_main = _head(r); assert new_main == a_integ

    # Pair B's c2 is now stale: its staging_base (base) != main.head (a_integ). The gate
    # REJECTs "stale" and does NOT move the ref — no double-write on the loser.
    r2 = run_gate("c2", store, r, registry_dir=reg, bus_id="prod", main_ref=MAIN)
    assert r2.outcome == "REJECTED" and "stale" in r2.reason, r2.reason
    assert _head(r) == new_main                        # gate did NOT write on the loser

    # Rework re-stages c2 as a NEW candidate: rebase branch_b onto the advanced main, then
    # stage with staging_base = new_main. The rebased branch (branch_b2) is a fresh commit,
    # so c2b's branch-bound preliminary attestation lands as its OWN per-candidate fact.
    _git(r, "checkout", "-q", "-b", "feat_b2", new_main)
    _git(r, "cherry-pick", branch_b)
    branch_b2 = _git(r, "rev-parse", "HEAD").stdout.strip()
    assert branch_b2 != branch_b
    b2_integ = _stage(r, new_main, branch_b2, "c2b")
    _populate(store, build_candidate_events(new_main, branch_b2, b2_integ, privs,
                                            pair=PAIR_B, candidate_id="c2b",
                                            allowed_paths=_ALLOW), privs, seen)
    r3 = run_gate("c2b", store, r, registry_dir=reg, bus_id="prod", main_ref=MAIN)
    assert r3.outcome == "COMPLETED", r3.reason
    assert _head(r) == b2_integ


def test_restage_is_load_bearing_stale_base_alone_stays_rejected(world_two_pairs):
    # Non-vacuity guard: the r3 COMPLETED above is genuinely due to RE-STAGING onto the
    # advanced main.head — NOT a candidate that would pass anyway. Here we re-invoke the
    # gate on the LOSER's ORIGINAL stale facts (the shape of a re-run that forgot to
    # re-stage); the gate must keep REJECTing "stale" and never move main.
    r, base, branch_a, branch_b, reg, privs = world_two_pairs
    store = RefEventStore(r)
    a_integ = _stage(r, base, branch_a, "c1")
    b_integ = _stage(r, base, branch_b, "c2")
    seen = _populate(store, build_candidate_events(base, branch_a, a_integ, privs,
                                                   pair=PAIR_A, candidate_id="c1",
                                                   allowed_paths=_ALLOW), privs)
    _populate(store, build_candidate_events(base, branch_b, b_integ, privs,
                                            pair=PAIR_B, candidate_id="c2",
                                            allowed_paths=_ALLOW), privs, seen)
    assert run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                    main_ref=MAIN).outcome == "COMPLETED"
    new_main = _head(r); assert new_main == a_integ

    # Re-invoke the gate on c2's loser facts WITHOUT re-staging (stale base survives):
    # still REJECTED "stale", main unmoved. So r3's COMPLETED is load-bearing on the
    # re-stage, not an artifact that would land on a stale base too.
    r_again = run_gate("c2", store, r, registry_dir=reg, bus_id="prod", main_ref=MAIN)
    assert r_again.outcome == "REJECTED" and "stale" in r_again.reason, r_again.reason
    assert _head(r) == new_main
