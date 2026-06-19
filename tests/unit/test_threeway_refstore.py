"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_refstore.py -q"""
import os
import subprocess

from threeway import keys
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
