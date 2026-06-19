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


# ---------------------------------------------------------------------------
# Write-side end-to-end (§6.4): exact-SHA CAS merge + idempotent recovery.
# ---------------------------------------------------------------------------
from threeway.store import EventStore
from threeway.gate import run_gate, GateResult


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True,
                          capture_output=True, text=True, env=_env())


@pytest.fixture()
def live_repo(tmp_path):
    """A repo with a protected test-main ref and a builder branch (clean merge)."""
    r = tmp_path / "repo"; r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@e.st"); _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "base")
    base = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", "refs/threeway/test-main", base)
    _git(r, "checkout", "-q", "-b", "feat")
    (r / "cinema").mkdir()
    (r / "cinema" / "foo.py").write_text("x = 1\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "feat")
    branch = _git(r, "rev-parse", "HEAD").stdout.strip()
    return r, base, branch


def _valid_events_for(base, branch, integ, privs, bus_id="prod"):
    """Build a complete, correctly-SIGNED T1 event set bound to real SHAs, via the
    Task-15 helper threeway.loop.build_candidate_events."""
    from threeway.loop import build_candidate_events
    return build_candidate_events(base, branch, integ, privs, bus_id=bus_id)


def test_run_gate_merges_clean_candidate_via_cas(live_repo, seatkit):
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    # stage: coordinator computes integration_sha via merge-tree+commit-tree, using
    # the SAME deterministic message the gate recomputes with ("threeway merge c1"),
    # so the gate's exact-SHA equality check passes.
    from threeway import gitcas
    tree, clean = gitcas.merge_tree(r, base, branch)
    assert clean
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge c1")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason
    # test-main now points at the merge commit
    new_head = _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip()
    assert new_head == integ
    # merge_completed fact emitted
    from threeway.gate import verify_and_reduce
    state = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
    assert state.merge_completed("c1") is not None


def test_run_gate_is_idempotent_under_double_invocation(live_repo, seatkit):
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    from threeway import gitcas
    tree, _ = gitcas.merge_tree(r, base, branch)
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge c1")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    r1 = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                  main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    r2 = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                  main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert r1.outcome == "COMPLETED" and r2.outcome == "COMPLETED"
    # exactly ONE merge_completed fact => no double write
    from threeway.gate import verify_and_reduce
    state = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
    completes = [e for e in store.all_events() if e.kind == "merge_completed"]
    assert len(completes) == 1


def test_run_gate_rejects_nonexistent_integration_sha_not_raises(live_repo, seatkit):
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    ghost = "0" * 39 + "1"                       # 40-hex, no such object
    events = _valid_events_for(base, branch, ghost, privs, bus_id="prod")
    for ev in events:
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "REJECTED", res.reason          # must NOT raise
    assert "integration_sha" in res.reason or "known commit" in res.reason
    # the protected ref must NOT have moved (fail-closed)
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == base


def test_run_gate_backstop_rejects_when_gate_side_plumbing_raises(
        live_repo, seatkit, monkeypatch):
    """F2 layer-2 (the gate backstop). The predicate's nonexistent-SHA guard checks
    integration_sha/staging_base but NOT the gate-side merge recompute: a residual
    git-plumbing failure on the attested SHA (e.g. commit_tree exit 128) must become
    a REJECTED GateResult, never an escaping CalledProcessError — run_gate stays TOTAL.

    The predicate guard (layer 1) and this backstop (layer 2) are independent; the
    existing F2 tests only reach REJECTED via the guard, so this drives a
    CalledProcessError PAST the predicate (all SHAs real -> MERGEABLE) and INTO the
    gate's recompute, where the except must catch it. (A ghost branch_sha cannot
    reach here: gitcas.merge_tree uses check=False and returns 'not clean' instead of
    raising, so we make the gate-side commit_tree raise directly.)"""
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    from threeway import gitcas
    tree, clean = gitcas.merge_tree(r, base, branch)
    assert clean
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge c1")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])

    # the predicate now reaches MERGEABLE; detonate the gate-side recompute exactly
    # where the backstop's try wraps it (the §6.4 commit_tree on the attested SHA).
    def _boom(*a, **k):
        raise subprocess.CalledProcessError(128, ["git", "commit-tree"])
    monkeypatch.setattr("threeway.gate.gitcas.commit_tree", _boom)

    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    # backstop did NOT let the exception escape; this is the gate's reason, not the
    # predicate guard's ("integration_sha is not a known commit").
    assert res.outcome == "REJECTED", res.reason
    assert "git plumbing failed on attested SHA" in res.reason
    # fail-closed: the protected ref did NOT move.
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == base
