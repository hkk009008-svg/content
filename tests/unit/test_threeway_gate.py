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


# ---------------------------------------------------------------------------
# Trust-boundary invariants (PURE test-only additions — guard the gate's
# signature-verification trust boundary as the reducer grows).
# ---------------------------------------------------------------------------
import ast
import pathlib

import threeway


def _reducer_consumed_kinds():
    """Extract every kind literal the reducer dispatches on, from its AST —
    so this invariant stays honest as reduce() grows. Looks for comparisons
    `k == "literal"` (and `ev.kind == "literal"`) inside reducer.py."""
    src = pathlib.Path(threeway.__file__).with_name("reducer.py").read_text()
    tree = ast.parse(src)
    kinds = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
            left, right = node.left, node.comparators[0]
            # match `<something> == "literal"` where literal is a str
            for a, b in ((left, right), (right, left)):
                if isinstance(b, ast.Constant) and isinstance(b.value, str):
                    # left side should reference k or ev.kind
                    if (isinstance(a, ast.Name) and a.id == "k") or \
                       (isinstance(a, ast.Attribute) and a.attr == "kind"):
                        kinds.add(b.value)
    return kinds


def test_every_reducer_consumed_kind_is_load_bearing():
    """SECURITY INVARIANT: any event kind that mutates effective state must be
    signature-verified. The gate verifies only LOAD_BEARING_KINDS, so a reducer
    branch on a non-load-bearing kind would be an unsigned-injection BYPASS.
    If this fails: you added an `elif k == "newkind"` to reducer.py — add
    "newkind" to threeway.LOAD_BEARING_KINDS (and confirm the gate should verify it)."""
    consumed = _reducer_consumed_kinds()
    assert consumed, "AST extraction found no reducer kinds — the extractor is broken, not the invariant"
    missing = consumed - threeway.LOAD_BEARING_KINDS
    assert not missing, f"reducer mutates state on non-load-bearing (UNVERIFIED) kinds: {sorted(missing)}"


def test_non_load_bearing_kind_passes_through_unverified(seatkit):
    reg, ks, privs = seatkit
    from threeway.envelope import Event
    # 'event_acknowledged' is in THREEWAY_KINDS but NOT LOAD_BEARING_KINDS:
    import threeway
    assert "event_acknowledged" in threeway.THREEWAY_KINDS
    assert "event_acknowledged" not in threeway.LOAD_BEARING_KINDS
    ev = Event(id="x1", seq=1, bus_id="prod", schema_version="threeway/1",
               kind="event_acknowledged", sender="operator", recipient="all",
               signer="operator:claude:s1", payload={})  # deliberately UNSIGNED
    # passes through without raising (non-load-bearing → not verified)
    state = verify_and_reduce([ev], registry_dir=reg, bus_id="prod")
    assert state is not None
