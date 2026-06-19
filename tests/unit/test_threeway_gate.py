"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_gate.py -q"""
import os
import subprocess

import pytest

from threeway import keys
from threeway.gate import verify_and_reduce, GateError


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
    for seat in ("director", "operator", "coordinator", "overseer", "ci", "merge-gate"):
        priv, pub = keys.generate_keypair()
        (reg / f"{seat}.pub").write_text(pub + "\n")
        (ks / f"{seat}.ed25519").write_text(keys.private_to_hex(priv) + "\n")
        privs[seat] = priv
    monkeypatch.setenv("THREEWAY_KEYSTORE", str(ks))
    return reg, ks, privs


def test_verify_and_reduce_rejects_unsigned_event(seatkit, tmp_path):
    reg, ks, privs = seatkit
    from threeway.envelope import Event
    ev = Event(id="e1", seq=1, bus_id="prod", schema_version="threeway/1",
               kind="candidate", sender="coordinator", recipient="all",
               signer="coordinator:claude:s1", payload={}, candidate_id="c1")
    # not signed
    with pytest.raises(GateError):
        verify_and_reduce([ev], registry_dir=reg, bus_id="prod")


def test_verify_and_reduce_rejects_bus_id_mismatch_replay(seatkit, tmp_path):
    reg, ks, privs = seatkit
    from threeway.envelope import Event, sign_event
    ev = Event(id="e1", seq=1, bus_id="TEST-BUS", schema_version="threeway/1",
               kind="candidate", sender="coordinator", recipient="all",
               signer="coordinator:claude:s1", payload={}, candidate_id="c1")
    sign_event(ev, privs["coordinator"])
    with pytest.raises(GateError, match="bus_id"):
        verify_and_reduce([ev], registry_dir=reg, bus_id="prod")


def test_verify_and_reduce_rejects_unknown_signer_seat(seatkit, tmp_path):
    reg, ks, privs = seatkit
    from threeway.envelope import Event, sign_event
    ev = Event(id="e1", seq=1, bus_id="prod", schema_version="threeway/1",
               kind="candidate", sender="ghost", recipient="all",
               signer="ghost:claude:s1", payload={}, candidate_id="c1")
    sign_event(ev, privs["coordinator"])  # signed by coordinator but claims ghost
    with pytest.raises(GateError):
        verify_and_reduce([ev], registry_dir=reg, bus_id="prod")


def test_verify_and_reduce_accepts_valid_signed_events(seatkit, tmp_path):
    reg, ks, privs = seatkit
    from threeway.envelope import Event, sign_event
    ev = Event(id="e1", seq=1, bus_id="prod", schema_version="threeway/1",
               kind="candidate", sender="coordinator", recipient="all",
               signer="coordinator:claude:s1", payload={"pair": "A"}, candidate_id="c1")
    sign_event(ev, privs["coordinator"])
    state = verify_and_reduce([ev], registry_dir=reg, bus_id="prod")
    assert state.candidate("c1") is not None
