"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_refstore.py -q"""
import hashlib
import json
import multiprocessing as mp
import os
import subprocess

import pytest

from threeway import gitcas, keys
from threeway.envelope import Event, idempotency_key, sign_event, to_json_obj, verify_event
from threeway.refstore import (
    AppendContentionExceeded,
    CursorContentionExceeded,
    CursorCorruptionError,
    IdempotencyKeyReused,
    RefEventStore,
)


def _env():
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    return env


def _git(repo, *args, **kw):
    return subprocess.run(["git", "-C", str(repo), *args],
                          check=True, capture_output=True, text=True,
                          env=_env(), **kw)


def _new_repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@e.st")
    _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "base")
    return r        # returns the repo PATH only (not the fixture's tuple)


def _new_bare(path):                       # the authoritative bus remote (spec §8)
    _git(path.parent, "init", "--bare", "-q", str(path))
    return path


def _clone(bare, dest):                    # a seat's working clone of the authority
    _git(dest.parent, "clone", "-q", str(bare), str(dest))
    _git(dest, "config", "user.email", "t@e.st")
    _git(dest, "config", "user.name", "t")
    return dest


def _signed(ev, priv):
    sign_event(ev, priv)
    return ev


def _verifies(ev, pub_hex):
    try:
        verify_event(ev, pub_hex)
        return True
    except Exception:
        return False


def _inject_raw_event(repo, ref, obj):
    """Hand-craft an event commit on `ref` that BYPASSES append, so the stored bytes
    can lie (e.g. a forged/tampered idempotency_key). Writes the event blob at
    events/<brief_id>/<id>.json + an index/<next-seq:08d> entry, extending the tip."""
    tip = gitcas.rev_parse(repo, ref)
    seqs = gitcas.list_index_seqs(repo, tip) if tip else []
    seq = (max(seqs) + 1) if seqs else 1
    event_path = f"events/{obj['brief_id']}/{obj['id']}.json"
    event_bytes = json.dumps(obj, ensure_ascii=False).encode()
    digest = hashlib.sha256(event_bytes).hexdigest()
    index_bytes = json.dumps(
        {"uuid": obj["id"], "path": event_path, "object_digest": digest},
        ensure_ascii=False).encode()
    index_path = f"index/{seq:08d}"
    blob_e = gitcas.write_blob(repo, event_bytes)
    blob_i = gitcas.write_blob(repo, index_bytes)
    base_tree = gitcas.tree_of(repo, tip) if tip else None
    tree = gitcas.build_tree_with(repo, base_tree,
                                  [(event_path, blob_e), (index_path, blob_i)])
    commit = gitcas.commit_on(repo, tree, tip, f"raw event {seq:08d}")
    assert gitcas.cas_create_or_update_ref(repo, ref, commit, tip) is True


def _unsigned(id="e", kind="attestation", signer="operator:claude:s1", **over):
    base = dict(id=id, seq=0, bus_id="prod", schema_version="threeway/1", kind=kind,
                sender="operator", recipient="all", signer=signer, payload={"k": id},
                brief_id="b1", brief_version=1)
    base.update(over)
    return Event(**base)        # signature_version defaults to "threeway-sign/2"


def test_append_assigns_monotonic_seq_from_one(tmp_path):
    r = _new_repo(tmp_path); priv, _ = keys.generate_keypair()
    store = RefEventStore(r)
    # distinct ids -> distinct payloads/idempotency keys -> two DISTINCT requests
    a = store.append(_unsigned(id="a", kind="attestation"), priv)
    b = store.append(_unsigned(id="b", kind="attestation"), priv)
    assert (a.seq, b.seq) == (1, 2)


def test_iter_events_returns_in_seq_order_and_verifies(tmp_path):
    r = _new_repo(tmp_path); priv, pub = keys.generate_keypair()
    store = RefEventStore(r)
    store.append(_unsigned(id="e1"), priv); store.append(_unsigned(id="e2"), priv)
    evs = store.all_events()
    assert [e.id for e in evs] == ["e1", "e2"]
    verify_event(evs[0], pub)                     # signed over its assigned seq


def test_seq_persists_across_store_reopen(tmp_path):
    r = _new_repo(tmp_path); priv, _ = keys.generate_keypair()
    RefEventStore(r).append(_unsigned(id="e1"), priv)
    again = RefEventStore(r).append(_unsigned(id="e2"), priv)
    assert again.seq == 2                          # tip-derived, durable


# ----------------------------------------------------------------------------
# H1 — iter_events() must be remote-safe (sync before reading) when called DIRECTLY
# (not only via all_events). Mutation check: drop the _sync from iter_events
# (`if self._remote is not None: self._sync()`) -> a fresh clone reads its empty
# local ref -> returns [] -> this test FAILS (proves the sync is load-bearing).
# ----------------------------------------------------------------------------
def test_iter_events_remote_mode_syncs_before_read(tmp_path):
    bare = _new_bare(tmp_path / "bus.git")
    c1 = _clone(bare, tmp_path / "c1"); priv, _ = keys.generate_keypair()
    RefEventStore(c1, remote="origin", sleeper=lambda _: None).append(
        _unsigned(id="e1"), priv)
    c2 = _clone(bare, tmp_path / "c2")             # SECOND fresh clone: empty local ref
    evs = list(RefEventStore(c2, remote="origin").iter_events())   # direct, NOT all_events
    assert [e.id for e in evs] == ["e1"]           # iter_events synced from authority


# ----------------------------------------------------------------------------
# Step 1a — deterministic forced-CAS-loss (LOCAL mode, one retry via _before_cas).
# ----------------------------------------------------------------------------
# Mutation check: drop the re-sign (move sign_event out of the retry loop / sign once
# before the loop) -> A stays signed over its FIRST seq(=1) but lands at seq=2 ->
# verify_event(evs["A"], pua) FAILS (the signature no longer covers the new seq).
def test_concurrent_append_loses_no_event_and_re_signs(tmp_path):
    r = _new_repo(tmp_path)
    pa, pua = keys.generate_keypair(); pb, pub_b = keys.generate_keypair()
    store = RefEventStore(r, sleeper=lambda _: None)
    fired = {"n": 0}; competitor = RefEventStore(r)
    def inject(attempt):
        if fired["n"] == 0:
            fired["n"] += 1
            competitor.append(_unsigned(id="B", signer="operator:codex:s1"), pb)
    a = store.append(_unsigned(id="A", signer="operator:claude:s1"), pa, _before_cas=inject)
    evs = {e.id: e for e in RefEventStore(r).all_events()}
    assert sorted(evs) == ["A", "B"]                 # neither lost, neither duplicated
    assert {evs["A"].seq, evs["B"].seq} == {1, 2}    # distinct, contiguous
    assert a.seq == 2                                # A re-seq'd after losing the first CAS
    verify_event(evs["A"], pua); verify_event(evs["B"], pub_b)   # A re-signed over seq=2


def test_append_raises_bounded_AppendContentionExceeded(tmp_path):
    r = _new_repo(tmp_path); p, _ = keys.generate_keypair(); op, _ = keys.generate_keypair()
    other = RefEventStore(r)
    # each steal is a NEW distinct event (distinct id -> distinct payload {"k": id} ->
    # distinct idempotency key, never colliding with the target "A"), so the target's
    # CAS keeps LOSING (not dedup-returning) until max_attempts is exhausted.
    def always_steal(attempt): other.append(_unsigned(id=f"x{attempt}"), op)
    store = RefEventStore(r, max_attempts=5, sleeper=lambda _: None)
    with pytest.raises(AppendContentionExceeded):
        store.append(_unsigned(id="A"), p, _before_cas=always_steal)


# ----------------------------------------------------------------------------
# Step 1b — GENUINE two-process race (the §11 GATE). Module-level worker so spawn
# can pickle it. A THREAD version is NOT a substitute for this gate.
# ----------------------------------------------------------------------------
def _race_worker(args):
    repo, ks, remote, seat, ids, barrier, retry_q = args
    os.environ["THREEWAY_KEYSTORE"] = ks
    from threeway.keys import load_private
    from threeway.refstore import RefEventStore
    store = RefEventStore(repo, remote=remote, sleeper=lambda _: None)
    priv = load_private(seat)
    attempts = {"n": 0}
    def count(_a): attempts["n"] += 1
    barrier.wait()
    for i in ids:
        store.append(_unsigned(id=i, signer=f"{seat}:p:s1"), priv, _before_cas=count)
    retry_q.put(attempts["n"] - len(ids))


# Mutation check: remove _sync() from the retry path (so a loser re-uses its stale tip)
# -> two processes commit on the SAME parent, one push-CAS wins and the other's events
# are silently overwritten -> the id-set / contiguous-seq assertions FAIL (loss).
def test_genuine_two_process_race_no_loss(tmp_path):
    ctx = mp.get_context("spawn")
    bare = _new_bare(tmp_path / "bus.git")
    c1 = _clone(bare, tmp_path / "c1"); c2 = _clone(bare, tmp_path / "c2")
    ks = tmp_path / "ks"; ks.mkdir(); pubs = {}
    for s in ("operator", "operator2"):
        priv, pub = keys.generate_keypair()
        (ks / f"{s}.ed25519").write_text(keys.private_to_hex(priv) + "\n"); pubs[s] = pub
    N = 8
    a_ids = [f"a{i}" for i in range(N)]; b_ids = [f"b{i}" for i in range(N)]
    barrier = ctx.Barrier(2); q = ctx.Queue()
    p1 = ctx.Process(target=_race_worker, args=((str(c1), str(ks), "origin", "operator",  a_ids, barrier, q),))
    p2 = ctx.Process(target=_race_worker, args=((str(c2), str(ks), "origin", "operator2", b_ids, barrier, q),))
    p1.start(); p2.start(); p1.join(60); p2.join(60)
    assert p1.exitcode == 0 and p2.exitcode == 0
    total_retries = q.get() + q.get()
    assert total_retries >= 1                              # a REAL race occurred (not serial)
    evs = RefEventStore(_clone(bare, tmp_path / "v"), remote="origin").all_events()
    assert {e.id for e in evs} == set(a_ids + b_ids)       # exact-once BY IDENTITY
    ikeys = [idempotency_key(e) for e in evs]
    assert len(set(ikeys)) == len(ikeys) == 2 * N          # no logical duplicate
    assert sorted(e.seq for e in evs) == list(range(1, 2 * N + 1))   # distinct, contiguous
    for e in evs:
        verify_event(e, pubs[e.signer.split(":", 1)[0]])


# ----------------------------------------------------------------------------
# Step 1c — Blocker-1 idempotency correctness.
# ----------------------------------------------------------------------------
def test_same_key_same_request_returns_original_event(tmp_path):
    r = _new_repo(tmp_path); p, _ = keys.generate_keypair(); s = RefEventStore(r)
    first = s.append(_unsigned(id="e1", payload={"k": "x"}), p)
    again = s.append(_unsigned(id="e1", payload={"k": "x"}), p)
    assert again.id == first.id and again.seq == first.seq and len(s.all_events()) == 1


# Mutation check: drop the fingerprint compare (return `existing` unconditionally on a
# key match) -> this DIFFERENT request (recipient "director" vs "all") is wrongly
# deduped to the first event instead of raising -> pytest.raises FAILS.
def test_same_key_different_request_is_rejected(tmp_path):
    r = _new_repo(tmp_path); p, _ = keys.generate_keypair(); s = RefEventStore(r)
    s.append(_unsigned(id="e1", recipient="all", payload={"k": "same"}), p)
    with pytest.raises(IdempotencyKeyReused):
        s.append(_unsigned(id="e2", recipient="director", payload={"k": "same"}), p)


# Mutation check: drop the signature verify in _find_verified_idempotent (treat any
# key match as a dup) -> the forged event (same key, signed by `evil`) suppresses the
# legitimate append -> the legit event is never written -> this test FAILS.
def test_invalid_signature_cannot_suppress_a_legitimate_append(tmp_path):
    r = _new_repo(tmp_path); p, ppub = keys.generate_keypair(); evil, _ = keys.generate_keypair()
    s = RefEventStore(r)
    s.append(_unsigned(id="forged", payload={"k": "x"}), evil)
    s.append(_unsigned(id="legit",  payload={"k": "x"}), p)
    legit = [e for e in s.all_events() if e.id == "legit"]
    assert legit and _verifies(legit[0], ppub)


# Mutation check: trust the serialized idempotency_key (read obj["idempotency_key"]
# instead of recomputing) -> the injected liar (claims target's key but its real fields
# differ) suppresses the legitimate append of "t" -> "t" never lands -> this test FAILS.
def test_tampered_stored_idempotency_key_is_not_trusted(tmp_path):
    r = _new_repo(tmp_path); p, _ = keys.generate_keypair(); s = RefEventStore(r)
    target = _unsigned(id="t", payload={"k": "real"})
    obj = to_json_obj(_signed(_unsigned(id="liar", payload={"k": "other"}), p))
    obj["idempotency_key"] = idempotency_key(target)
    _inject_raw_event(r, "refs/threeway/events", obj)
    landed = s.append(target, p)
    assert any(e.id == "t" for e in s.all_events()) and landed.id == "t"


def _same_fact_worker(args):
    repo, ks, remote, evid, barrier = args
    os.environ["THREEWAY_KEYSTORE"] = ks
    from threeway.keys import load_private
    from threeway.refstore import RefEventStore
    s = RefEventStore(repo, remote=remote, sleeper=lambda _: None)
    barrier.wait()
    s.append(_unsigned(id=evid, payload={"k": "same"}, signer="operator:p:s1"), load_private("operator"))


# Mutation check: remove _sync() from the retry path -> both processes start from an
# empty local ref, neither sees the other's event during the idempotency scan, both
# create distinct seqs for the SAME logical fact -> len(same) == 2 -> this test FAILS.
def test_two_processes_same_key_create_exactly_one_event(tmp_path):
    ctx = mp.get_context("spawn")
    bare = _new_bare(tmp_path / "bus.git")
    c1 = _clone(bare, tmp_path / "c1"); c2 = _clone(bare, tmp_path / "c2")
    ks = tmp_path / "ks"; ks.mkdir()
    priv, _ = keys.generate_keypair()
    (ks / "operator.ed25519").write_text(keys.private_to_hex(priv) + "\n")
    target_key = idempotency_key(_unsigned(id="x", payload={"k": "same"}, signer="operator:p:s1"))
    barrier = ctx.Barrier(2)
    p1 = ctx.Process(target=_same_fact_worker, args=((str(c1), str(ks), "origin", "dupA", barrier),))
    p2 = ctx.Process(target=_same_fact_worker, args=((str(c2), str(ks), "origin", "dupB", barrier),))
    p1.start(); p2.start(); p1.join(60); p2.join(60)
    assert p1.exitcode == 0 and p2.exitcode == 0
    evs = RefEventStore(_clone(bare, tmp_path / "v"), remote="origin").all_events()
    same = [e for e in evs if idempotency_key(e) == target_key]
    assert len(same) == 1


# ----------------------------------------------------------------------------
# Step 1d — genuine ambiguous remote push recovers via a FRESH clone.
# ----------------------------------------------------------------------------
# Mutation check: remove _sync() from the retry/scan path (so the fresh clone never
# fetches the authoritative tip before its idempotency scan) -> the fresh clone re-adds
# the same fact -> len(...) == 2 -> this test FAILS (the recovery dedup relies on sync).
def test_ambiguous_remote_push_recovers_via_fresh_clone(tmp_path):
    bare = _new_bare(tmp_path / "bus.git"); c1 = _clone(bare, tmp_path / "c1")
    priv, _ = keys.generate_keypair()
    s1 = RefEventStore(c1, remote="origin", sleeper=lambda _: None)
    def boom(_): raise RuntimeError("connection dropped AFTER the remote accepted")
    with pytest.raises(RuntimeError):
        s1.append(_unsigned(id="e1", payload={"k": "x"}, signer="operator:p:s1"), priv, _after_cas=boom)
    c2 = _clone(bare, tmp_path / "c2")                      # fresh process: no local state
    RefEventStore(c2, remote="origin", sleeper=lambda _: None).append(
        _unsigned(id="e1b", payload={"k": "x"}, signer="operator:p:s1"), priv)   # same fact
    evs = RefEventStore(_clone(bare, tmp_path / "v"), remote="origin").all_events()
    assert len([e for e in evs if e.payload.get("k") == "x"]) == 1   # landed exactly once


def test_local_timed_out_retry_is_idempotent(tmp_path):
    r = _new_repo(tmp_path); p, _ = keys.generate_keypair(); s = RefEventStore(r)
    first = s.append(_unsigned(id="e1"), p)
    again = s.append(_unsigned(id="e1"), p)
    assert len(s.all_events()) == 1 and again.seq == first.seq
