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
    # operator2 = mirror pair-B primary_verifier (T2 co_sign); chief-* = ADR-043 key-bound
    # T3 human approvers (each needs its OWN registry key or its approval is dropped as an
    # unknown signer seat — the operational precondition pinned by the T3 gate tests below).
    for seat in ("director", "operator", "operator2", "coordinator", "overseer", "ci",
                 "merge-gate", "chief-gemini", "chief-chatgpt"):
        priv, pub = keys.generate_keypair()
        (reg / f"{seat}.pub").write_text(pub + "\n")
        (ks / f"{seat}.ed25519").write_text(keys.private_to_hex(priv) + "\n")
        privs[seat] = priv
    monkeypatch.setenv("THREEWAY_KEYSTORE", str(ks))
    return reg, ks, privs


def test_verify_and_reduce_drops_unsigned_event(seatkit, tmp_path):
    # ADR-040: a load-bearing event with a missing/invalid signature is DROPPED (not raised),
    # so the fact it would have carried is ABSENT from effective state. Dropping is fail-safe:
    # an unsigned event has no authority, so this can only REMOVE it, never admit a forged fact.
    reg, ks, privs = seatkit
    from threeway.envelope import Event
    ev = Event(id="e1", seq=1, bus_id="prod", schema_version="threeway/1",
               kind="candidate", sender="coordinator", recipient="all",
               signer="coordinator:claude:s1", payload={"pair": "A"}, candidate_id="A:c1")
    # not signed -> dropped at the signature check; no raise.
    state = verify_and_reduce([ev], registry_dir=reg, bus_id="prod")
    assert state.candidate("A:c1") is None   # the unsigned candidate never entered effective state


def test_verify_and_reduce_drops_bus_id_mismatch_replay(seatkit, tmp_path):
    # ADR-040: a load-bearing event from the WRONG bus (replay) is DROPPED, not raised — one
    # forged wrong-bus event must not brick verify_and_reduce for every candidate. The fact is absent.
    reg, ks, privs = seatkit
    from threeway.envelope import Event, sign_event
    ev = Event(id="e1", seq=1, bus_id="TEST-BUS", schema_version="threeway/1",
               kind="candidate", sender="coordinator", recipient="all",
               signer="coordinator:claude:s1", payload={"pair": "A"}, candidate_id="A:c1")
    sign_event(ev, privs["coordinator"])
    state = verify_and_reduce([ev], registry_dir=reg, bus_id="prod")
    assert state.candidate("A:c1") is None   # wrong-bus replay dropped; never reduced


def test_verify_and_reduce_drops_unknown_signer_seat(seatkit, tmp_path):
    # ADR-040: a load-bearing event signed by an UNKNOWN seat (no registry key) is DROPPED, not
    # raised. An unknown seat has no authority, so the fact is simply absent.
    reg, ks, privs = seatkit
    from threeway.envelope import Event, sign_event
    ev = Event(id="e1", seq=1, bus_id="prod", schema_version="threeway/1",
               kind="candidate", sender="ghost", recipient="all",
               signer="ghost:claude:s1", payload={"pair": "A"}, candidate_id="A:c1")
    sign_event(ev, privs["coordinator"])  # signed by coordinator's key but claims ghost
    state = verify_and_reduce([ev], registry_dir=reg, bus_id="prod")
    assert state.candidate("A:c1") is None   # unknown-seat event dropped; never reduced


def test_gate_drops_unknown_signature_version(seatkit, tmp_path):
    # ADR-040: a load-bearing event presenting an UNACCEPTED signature_version is DROPPED, not
    # raised. The fact is absent (a weaker/forged profile has no authority).
    reg, ks, privs = seatkit
    from threeway.envelope import Event, sign_event
    ev = Event(id="e1", seq=1, bus_id="prod", schema_version="threeway/1",
               kind="candidate", sender="coordinator", recipient="all",
               signer="coordinator:claude:s1", payload={"pair": "A"}, candidate_id="A:c1",
               signature_version="threeway-sign/1")   # unaccepted signature profile
    sign_event(ev, privs["coordinator"])               # validly signed under the old profile
    state = verify_and_reduce([ev], registry_dir=reg, bus_id="prod")
    assert state.candidate("A:c1") is None   # unaccepted-profile event dropped; never reduced


def test_verify_and_reduce_accepts_valid_signed_events(seatkit, tmp_path):
    reg, ks, privs = seatkit
    from threeway.envelope import Event, sign_event
    ev = Event(id="e1", seq=1, bus_id="prod", schema_version="threeway/1",
               kind="candidate", sender="coordinator", recipient="all",
               signer="coordinator:claude:s1", payload={"pair": "A"}, candidate_id="A:c1")
    sign_event(ev, privs["coordinator"])
    state = verify_and_reduce([ev], registry_dir=reg, bus_id="prod")
    assert state.candidate("A:c1") is not None


def test_verify_and_reduce_rejects_duplicate_event_id(seatkit, tmp_path):
    # ADR-037: event id is signed but NOT globally unique; a duplicate id across the
    # load-bearing set is a collision/replay (an insider re-using a victim fact's id to
    # shadow it) and must fail closed.
    reg, ks, privs = seatkit
    from threeway.envelope import Event, sign_event
    victim = Event(id="DUP", seq=1, bus_id="prod", schema_version="threeway/1",
                   kind="co_sign", sender="operator", recipient="all",
                   signer="operator:claude:s1", payload={"verdict": "GO"},
                   candidate_id="A:c1", subject_sha="2" * 40)
    sign_event(victim, privs["operator"])
    decoy = Event(id="DUP", seq=2, bus_id="prod", schema_version="threeway/1",
                  kind="attestation", sender="director", recipient="all",
                  signer="director:claude:s1", payload={"kind": "release", "verdict": "GO"},
                  candidate_id="A:c1", subject_sha="2" * 40)
    sign_event(decoy, privs["director"])   # each event validly signed by its OWN seat
    with pytest.raises(GateError, match="duplicate event id"):
        verify_and_reduce([victim, decoy], registry_dir=reg, bus_id="prod")


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
    # the SAME deterministic message the gate recomputes with ("threeway merge A:c1"),
    # so the gate's exact-SHA equality check passes.
    from threeway import gitcas
    tree, clean = gitcas.merge_tree(r, base, branch)
    assert clean
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge A:c1")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason
    # test-main now points at the merge commit
    new_head = _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip()
    assert new_head == integ
    # merge_completed fact emitted
    from threeway.gate import verify_and_reduce
    state = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
    assert state.merge_completed("A:c1") is not None


def test_run_gate_does_not_promote_candidate_shadow(live_repo, seatkit):
    # ADR-039 candidate shadow-DoS (gate side): a validly-signed shadow candidate from a
    # NON-coordinator seat (operator), higher seq, carrying ATTACKER base/branch/integ, is on
    # the bus alongside the legit promotion. The gate's step-4 trusted recompute must use the
    # AUTHORITATIVE candidate (signed by the assignment's executing_coordinator) and merge the
    # legit integration_sha — never the shadow's SHAs (a promotion forgery if gate.py recomputed
    # from the latest-seat candidate). It must also NOT be derailed into PENDING by the shadow.
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    from threeway import gitcas
    tree, clean = gitcas.merge_tree(r, base, branch)
    assert clean
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge A:c1")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    # the shadow uses a DISTINCT id (sender=operator) so it does not trip the dup-id guard;
    # it is a legitimate insider event the gate must IGNORE on authority grounds.
    from threeway.envelope import Event
    from threeway.policy import default_policy
    shadow = Event(id="candidate-operator-c1", seq=0, bus_id="prod",
                   schema_version="threeway/1", kind="candidate", sender="operator",
                   recipient="all", signer="operator:claude:s1",
                   payload={"pair": "A", "staging_base_sha": "a" * 40,
                            "branch_sha": "b" * 40, "integration_sha": "c" * 40,
                            "risk_tier_claimed": "T1",
                            "policy_digest": default_policy().policy_digest()},
                   candidate_id="A:c1", subject_sha="c" * 40)
    store.append(shadow, privs["operator"])
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason
    # main moved to the AUTHORITATIVE integration_sha, never the shadow's "c"*40.
    new_head = _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip()
    assert new_head == integ
    assert new_head != "c" * 40


def test_run_gate_survives_poisoned_reserved_merge_id(live_repo, seatkit):
    # ADR-039 availability win (supersedes the old ADR-037 reserved-id REJECT): an insider
    # pre-claims the predictable completion id 'merge-A:c1' (here a forged co_sign). The OLD
    # behavior REJECTED the whole candidate — but that handed any insider a per-candidate DoS
    # (squat the id, block every legit merge forever). The NEW behavior is strictly MORE
    # available: verify_and_reduce DROPS the squat at ingestion (reserved 'merge-' namespace is
    # reserved to the gate seat, so a non-gate event with that id is ignored, never reduced),
    # so the legit merge PROCEEDS and main MOVES. The gate's own post-CAS merge_completed append
    # then collides with the squatted id (EventIdCollision); because run_gate is TOTAL the
    # collision degrades to a COMPLETED-with-degraded-reason instead of crashing after main moved.
    # The squat can no longer block the merge; it only forfeits the completion FACT (recovery
    # then leans on the main-state idempotency check on a later clean re-run).
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    from threeway import gitcas
    tree, clean = gitcas.merge_tree(r, base, branch)
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge A:c1")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    from threeway.envelope import Event
    poison = Event(id="merge-A:c1", seq=0, bus_id="prod", schema_version="threeway/1",
                   kind="co_sign", sender="operator", recipient="all",
                   signer="operator:claude:s1", payload={"verdict": "GO"},
                   candidate_id="A:c1", subject_sha=integ)
    store.append(poison, privs["operator"])
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    # the squat does NOT block the legit merge: it COMPLETED (degraded) and main MOVED to integ.
    assert res.outcome == "COMPLETED", res.reason
    assert "degraded" in res.reason
    head_after = _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip()
    assert head_after == integ   # main DID move to the legit merge — the squat can't DoS it


def test_run_gate_drops_nongate_reserved_id_event(live_repo, seatkit):
    # ADR-039 reserved-namespace DROP (read-side): a non-gate seat presenting an event whose id
    # is in the reserved 'merge-' namespace is an insider squat. verify_and_reduce must IGNORE it
    # for reduction (drop, not raise — raising would let one forged 'merge-x' brick the gate for
    # EVERY candidate). Here a forged co_sign GO with id 'merge-A:c1' from operator must NOT surface
    # as a co_sign in effective state. (Mutation check: without the drop, state.co_sign would
    # return it, since each event is validly self-signed.)
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    from threeway import gitcas
    tree, clean = gitcas.merge_tree(r, base, branch)
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge A:c1")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    from threeway.envelope import Event
    smuggled = Event(id="merge-A:c1", seq=0, bus_id="prod", schema_version="threeway/1",
                     kind="co_sign", sender="operator", recipient="all",
                     signer="operator:claude:s1", payload={"verdict": "GO"},
                     candidate_id="A:c1", subject_sha=integ)
    store.append(smuggled, privs["operator"])
    state = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
    # the smuggled reserved-id co_sign was dropped at ingestion, never reduced.
    assert state.co_sign("c1", "operator") is None


def test_run_gate_total_under_post_cas_append_failure(live_repo, seatkit, monkeypatch):
    # ADR-039 totality: a post-CAS failure on the merge_completed append (here a non-
    # CalledProcessError raised by store.append, e.g. a keystore error) must NOT escape after
    # the irreversible CAS — main already moved. run_gate catches ALL exceptions in the post-CAS
    # block and degrades to COMPLETED. The pre-CAS recompute path is unaffected (still REJECTs a
    # CalledProcessError), so we only detonate the FINAL append, after the valid events are stored.
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    from threeway import gitcas
    tree, clean = gitcas.merge_tree(r, base, branch)
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge A:c1")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])

    # detonate ONLY the merge_completed append (the post-CAS one). The valid events are already
    # stored above, so wrapping append now affects only the gate's own completion-fact write.
    real_append = store.append
    def _boom(ev, private_key):
        if ev.kind == "merge_completed":
            raise RuntimeError("keystore unavailable")
        return real_append(ev, private_key)
    monkeypatch.setattr(store, "append", _boom)

    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason   # did NOT raise; degraded gracefully
    assert "degraded" in res.reason
    # main IS at the merge — the CAS landed before the append blew up (fail-OPEN is correct here:
    # the merge genuinely happened; only the recording was lost).
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ


def test_run_gate_main_state_idempotency_without_fact(live_repo, seatkit):
    # ADR-039 main-state idempotency: after a successful merge, if the merge_completed FACT is
    # missing (a post-CAS recording failure) but main is ALREADY at the authoritative candidate's
    # integration_sha, the merge LANDED — run_gate must return COMPLETED via the main-state check,
    # never a permanent stale REJECT. We simulate the lost fact by deleting the merge_completed
    # event file from the store after a successful merge, then re-running.
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    events_dir = r / "coordination" / "threeway" / "events"
    store = EventStore(events_dir)
    from threeway import gitcas
    tree, clean = gitcas.merge_tree(r, base, branch)
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge A:c1")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    r1 = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                  main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert r1.outcome == "COMPLETED", r1.reason
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ

    # withhold the recorded fact: delete the merge_completed event file (post-CAS-fail simulation).
    import pathlib
    removed = 0
    for p in pathlib.Path(events_dir).glob("*-merge-A:c1.json"):
        p.unlink(); removed += 1
    assert removed == 1, "expected exactly one merge_completed fact to withhold"
    # sanity: the fact is now gone from effective state.
    state = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
    assert state.merge_completed("A:c1") is None

    # re-run: no fact, but main==integ -> COMPLETED via main-state idempotency, not a stale REJECT.
    r2 = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                  main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert r2.outcome == "COMPLETED", r2.reason
    assert "idempotent" in r2.reason


def test_run_gate_is_idempotent_under_double_invocation(live_repo, seatkit):
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    from threeway import gitcas
    tree, _ = gitcas.merge_tree(r, base, branch)
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge A:c1")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    r1 = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                  main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    r2 = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
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
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
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
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge A:c1")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])

    # the predicate now reaches MERGEABLE; detonate the gate-side recompute exactly
    # where the backstop's try wraps it (the §6.4 commit_tree on the attested SHA).
    def _boom(*a, **k):
        raise subprocess.CalledProcessError(128, ["git", "commit-tree"])
    monkeypatch.setattr("threeway.gate.gitcas.commit_tree", _boom)

    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    # backstop did NOT let the exception escape; this is the gate's reason, not the
    # predicate guard's ("integration_sha is not a known commit"). ADR-040: the gate-side
    # recompute is PRE-CAS, so the broadened outer except now reports it as "pre-CAS error
    # ... git plumbing"; the fail-closed REJECTED (and the unmoved ref) is unchanged.
    assert res.outcome == "REJECTED", res.reason
    assert "pre-CAS error" in res.reason and "git plumbing" in res.reason
    # fail-closed: the protected ref did NOT move.
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == base


def test_run_gate_idempotent_with_non_default_gate_seat(live_repo, seatkit):
    """ADR-039 coupling regression: run_gate must thread its gate_seat all the way
    through verify_and_reduce -> reduce, so the reducer's record-time authority filter
    accepts the gate's OWN merge_completed fact (signed f"{gate_seat}:mech:gate"). If
    gate_seat is NOT threaded, reduce falls back to the module default GATE_SEAT="merge-gate"
    and DROPS a custom-gate-signed completion fact as unauthorized, so the idempotency no-op
    breaks and a crash-recovery re-run re-merges (or degrades) instead of being a clean
    at-most-once no-op. Part of the ADR-036/037/038/039 forgery+availability class."""
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    # register a NON-default gate seat in BOTH the public registry (so verify_and_reduce
    # can verify the load-bearing merge_completed fact) and the keystore (so the gate can
    # sign it via load_private(gate_seat)).
    from threeway import keys
    cg_priv, cg_pub = keys.generate_keypair()
    (reg / "custom-gate.pub").write_text(cg_pub + "\n")
    (ks / "custom-gate.ed25519").write_text(keys.private_to_hex(cg_priv) + "\n")

    store = EventStore(r / "coordination" / "threeway" / "events")
    from threeway import gitcas
    tree, clean = gitcas.merge_tree(r, base, branch)
    assert clean
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge A:c1")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])

    r1 = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                  main_ref="refs/threeway/test-main", gate_seat="custom-gate")
    assert r1.outcome == "COMPLETED", r1.reason

    # crash-recovery re-run: the gate's own custom-gate-signed merge_completed fact must be
    # HONORED by the reducer -> a clean idempotent no-op, NOT a reserved-id REJECT.
    r2 = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                  main_ref="refs/threeway/test-main", gate_seat="custom-gate")
    assert r2.outcome == "COMPLETED", r2.reason
    assert "idempotent" in r2.reason

    # exactly ONE merge_completed fact => no double merge under the custom seat
    completes = [e for e in store.all_events() if e.kind == "merge_completed"]
    assert len(completes) == 1

    # verify_and_reduce itself threads gate_seat so the completion fact is honored; with
    # the default seat the same bus DROPS it (proving threading is load-bearing).
    from threeway.gate import verify_and_reduce
    honored = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod",
                                gate_seat="custom-gate")
    assert honored.merge_completed("A:c1") is not None
    dropped = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
    assert dropped.merge_completed("A:c1") is None


# ---------------------------------------------------------------------------
# ADR-040: run_gate TOTALITY — verify-phase DROP-not-raise + pre-CAS guard.
#
# ADR-039 made verify_and_reduce DROP a reserved-`merge-` id squat instead of
# raising (so one forged event could not brick the whole bus). But FOUR sibling
# read-side checks were left RAISING (Rule #13 miss): bus_id mismatch, unaccepted
# signature_version, unknown signer seat, invalid signature. The raise is OUTSIDE
# run_gate's try, so an insider could append a validly-self-signed LOAD-BEARING
# event that trips one of these and brick run_gate for EVERY candidate. These
# tests pin: such a poison is DROPPED (ignored for reduction), the legit merge
# still proceeds, and run_gate never raises. (A dropped event has no authority,
# so dropping can only ever REMOVE an event — never admit a forged fact.)
# ---------------------------------------------------------------------------

def _seed_valid(store, r, privs, candidate_id="A:c1"):
    """Stage a complete, signed T1 promotion bound to a real clean merge. Returns integ."""
    from threeway import gitcas
    tree, clean = gitcas.merge_tree(r, "refs/threeway/test-main", "feat")
    assert clean
    base = _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip()
    branch = _git(r, "rev-parse", "feat").stdout.strip()
    integ = gitcas.commit_tree(r, tree, [base, branch], f"threeway merge {candidate_id}")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    return base, branch, integ


def test_run_gate_total_under_poison_wrong_bus_id(live_repo, seatkit):
    # An insider appends a load-bearing co_sign validly self-signed by a registered seat
    # (operator) but carrying bus_id="EVIL" (an ordinary non-reserved id). Pre-ADR-040 this
    # RAISED a GateError outside run_gate's try -> run_gate crashes for EVERY candidate.
    # ADR-040: the wrong-bus event is DROPPED; the legit merge proceeds and main moves.
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    _, _, integ = _seed_valid(store, r, privs)
    from threeway.envelope import Event
    poison = Event(id="cosign-operator-c1", seq=0, bus_id="EVIL",
                   schema_version="threeway/1", kind="co_sign", sender="operator",
                   recipient="all", signer="operator:claude:s1",
                   payload={"verdict": "GO"}, candidate_id="A:c1", subject_sha=integ)
    store.append(poison, privs["operator"])
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason   # did NOT raise; poison dropped
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ


def test_run_gate_poison_does_not_brick_other_candidates(live_repo, seatkit):
    # TOTAL-BUS property: with a wrong-bus_id poison present, a SECOND run_gate invocation
    # (here re-asserting c1; c1 is already merged so this exercises the idempotency path
    # AFTER verify_and_reduce, which must NOT raise on the poison). The poison cannot brick
    # the bus for any candidate.
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    _, _, integ = _seed_valid(store, r, privs)
    from threeway.envelope import Event
    poison = Event(id="cosign-operator-c1", seq=0, bus_id="EVIL",
                   schema_version="threeway/1", kind="co_sign", sender="operator",
                   recipient="all", signer="operator:claude:s1",
                   payload={"verdict": "GO"}, candidate_id="A:c1", subject_sha=integ)
    store.append(poison, privs["operator"])
    r1 = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                  main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert r1.outcome == "COMPLETED", r1.reason
    # the poison is STILL on the bus; a re-run must not raise (totality holds per-invocation).
    r2 = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                  main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert r2.outcome == "COMPLETED", r2.reason   # idempotent, did NOT raise on the poison


def test_run_gate_total_under_unknown_signer_seat(live_repo, seatkit):
    # An insider holds the operator key but stamps signer="ghost:claude:s1" (an unregistered
    # seat). reg.get("ghost") -> KeyError. Pre-ADR-040 this RAISED outside run_gate's try.
    # ADR-040: the event is DROPPED (unknown seat has no authority anyway), legit merge completes.
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    _, _, integ = _seed_valid(store, r, privs)
    from threeway.envelope import Event
    poison = Event(id="cosign-ghost-c1", seq=0, bus_id="prod",
                   schema_version="threeway/1", kind="co_sign", sender="ghost",
                   recipient="all", signer="ghost:claude:s1",
                   payload={"verdict": "GO"}, candidate_id="A:c1", subject_sha=integ)
    store.append(poison, privs["operator"])   # signed with a REGISTERED key but claims 'ghost'
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason   # did NOT raise; unknown-seat event dropped
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ


def test_run_gate_total_under_unaccepted_signature_version(live_repo, seatkit):
    # A load-bearing event presenting an unaccepted signature_version ("threeway-sign/1").
    # Pre-ADR-040 this RAISED outside run_gate's try. ADR-040: DROPPED, legit merge completes.
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    _, _, integ = _seed_valid(store, r, privs)
    from threeway.envelope import Event
    poison = Event(id="cosign-operator-oldprofile-c1", seq=0, bus_id="prod",
                   schema_version="threeway/1", kind="co_sign", sender="operator",
                   recipient="all", signer="operator:claude:s1",
                   payload={"verdict": "GO"}, candidate_id="A:c1", subject_sha=integ,
                   signature_version="threeway-sign/1")
    store.append(poison, privs["operator"])   # validly signed under the old (unaccepted) profile
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason   # did NOT raise; unaccepted-profile event dropped
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ


def test_run_gate_total_under_malformed_authoritative_candidate(live_repo, seatkit):
    # ADR-040 Fix 2 (pre-CAS totality): a validly-signed authoritative candidate with a
    # MISSING payload key makes evaluate() raise an uncaught KeyError that escapes run_gate's
    # narrow `except subprocess.CalledProcessError`. The broadened outer except catches ANY
    # pre-CAS error -> REJECTED (fail-closed; main is unmoved, the crash is before any merge).
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    base_sha, branch_sha, integ = _seed_valid(store, r, privs)
    from threeway.policy import default_policy
    from threeway.envelope import Event
    # a HIGHER-seq candidate signed by the assignment's executing_coordinator (coordinator)
    # becomes authoritative; drop staging_base_sha from its payload -> evaluate() KeyErrors.
    malformed = Event(id="candidate-coordinator-malformed-c1", seq=0, bus_id="prod",
                      schema_version="threeway/1", kind="candidate", sender="coordinator",
                      recipient="all", signer="coordinator:claude:s1",
                      payload={"pair": "A", "branch_sha": branch_sha,
                               "integration_sha": integ, "risk_tier_claimed": "T1",
                               "policy_digest": default_policy().policy_digest()},
                      candidate_id="A:c1", subject_sha=integ)   # NO staging_base_sha
    store.append(malformed, privs["coordinator"])
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "REJECTED", res.reason   # did NOT raise
    assert "malformed" in res.reason or "pre-CAS" in res.reason
    # fail-closed: main did NOT move (the crash is pre-CAS).
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == base_sha


# ---------------------------------------------------------------------------
# ADR-041: reduce() TOTALITY against malformed insider input. An insider seat validly
# self-signs a load-bearing event whose KEYED field is an unhashable JSON list (here a
# co_sign with candidate_id=["totally","unrelated"]). The field is signed, so no forgery
# is needed. Pre-ADR-041 reduce() raised TypeError (unhashable type: 'list') which escaped
# verify_and_reduce -> run_gate's step-1 call (OUTSIDE its try) -> a total-bus brick: ONE
# such event crashed run_gate for EVERY candidate, including a fully-legit independent one.
# The fix DROPS the malformed event; the legit merge COMPLETES and the bus stays total.
# ---------------------------------------------------------------------------

def test_run_gate_total_under_unhashable_keyed_field(live_repo, seatkit):
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    _, _, integ = _seed_valid(store, r, privs)   # a complete, signed, legit T1 promotion for c1
    from threeway.envelope import Event
    # an insider appends a VALIDLY-self-signed co_sign whose candidate_id is an unhashable list.
    # reduce() keys _co_sign by (candidate_id, seat) -> TypeError pre-fix. (Distinct, non-reserved
    # id so it is not dropped by the reserved-namespace / dup-id guards — only the ADR-041 drop.)
    poison = Event(id="cosign-poison-unhashable", seq=0, bus_id="prod",
                   schema_version="threeway/1", kind="co_sign", sender="operator",
                   recipient="all", signer="operator:claude:s1",
                   payload={"verdict": "GO"},
                   candidate_id=["totally", "unrelated"], subject_sha=integ)
    store.append(poison, privs["operator"])
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason   # did NOT raise; poison dropped, legit merge ran
    # main moved to the legit integration_sha — the poison could not brick the merge (total bus).
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ
    # the poison co_sign is ABSENT from effective state (dropped, never reduced); the legit
    # state is intact (verify_and_reduce did not raise on the unhashable keyed field).
    from threeway.gate import verify_and_reduce
    state = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
    assert state.merge_completed("A:c1") is not None


# ---------------------------------------------------------------------------
# ADR-041 (read-path completion): the reduce()-side totality fix is NOT enough. A
# validly-self-signed `candidate` whose payload["pair"] is an unhashable JSON list PASSES
# reduce() (the candidate fold keys only on (candidate_id, _seat_of(signer)) — both well-
# formed — so it enters _candidates). The brick is later: run_gate step-2a calls
# state.authoritative_candidate(candidate_id) OUTSIDE run_gate's try, and that loop calls
# self.assignment(c.payload.get("pair")) -> self._assignments.get([...]) -> TypeError
# (unhashable type: 'list') UNCAUGHT -> escapes run_gate. Iterating highest-seq-first, a
# high-seq poison candidate is reached before the legit one and bricks the victim's merge
# permanently (insider-targeted availability DoS, same class this slice closes). The fix
# SKIPS a candidate whose pair is not a str inside the loop (in-loop continue, not a wrap),
# so the legit candidate is still found and the merge COMPLETES.
# ---------------------------------------------------------------------------

def test_run_gate_total_under_unhashable_candidate_pair(live_repo, seatkit):
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    _, _, integ = _seed_valid(store, r, privs)   # legit c1 promotion (coordinator-signed candidate)
    from threeway.envelope import Event
    from threeway.policy import default_policy
    # an insider (operator) validly self-signs a HIGHER-seq candidate for the SAME id c1 whose
    # payload["pair"] is an unhashable list. Distinct, non-reserved id so it survives the
    # dup-id / reserved-namespace guards and reaches _candidates. authoritative_candidate()
    # iterates highest-seq-first -> hits this poison before the legit candidate.
    poison = Event(id="candidate-operator-listpair-c1", seq=0, bus_id="prod",
                   schema_version="threeway/1", kind="candidate", sender="operator",
                   recipient="all", signer="operator:claude:s1",
                   payload={"pair": ["A", "B"], "staging_base_sha": "a" * 40,
                            "branch_sha": "b" * 40, "integration_sha": "c" * 40,
                            "risk_tier_claimed": "T1",
                            "policy_digest": default_policy().policy_digest()},
                   candidate_id="A:c1", subject_sha="c" * 40)
    store.append(poison, privs["operator"])
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason   # did NOT raise; poison skipped, legit merge ran
    # main moved to the legit integration_sha — the list-pair poison could not brick the merge.
    new_head = _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip()
    assert new_head == integ
    assert new_head != "c" * 40


def test_authoritative_candidate_skips_unhashable_pair(live_repo, seatkit):
    # Reducer-level: authoritative_candidate returns the LEGIT candidate (does not raise) when a
    # higher-seq list-pair poison candidate is present for the same id.
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    _, _, integ = _seed_valid(store, r, privs)
    from threeway.envelope import Event
    from threeway.policy import default_policy
    from threeway.gate import verify_and_reduce
    poison = Event(id="candidate-operator-listpair2-c1", seq=0, bus_id="prod",
                   schema_version="threeway/1", kind="candidate", sender="operator",
                   recipient="all", signer="operator:claude:s1",
                   payload={"pair": ["A", "B"], "staging_base_sha": "a" * 40,
                            "branch_sha": "b" * 40, "integration_sha": "c" * 40,
                            "risk_tier_claimed": "T1",
                            "policy_digest": default_policy().policy_digest()},
                   candidate_id="A:c1", subject_sha="c" * 40)
    store.append(poison, privs["operator"])
    state = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
    auth = state.authoritative_candidate("A:c1")   # must NOT raise TypeError
    assert auth is not None
    # the legit (coordinator-signed, str-pair) candidate is authoritative, never the list-pair poison.
    assert auth.payload.get("pair") == "A"
    assert auth.signer.split(":", 1)[0] == "coordinator"


# ---------------------------------------------------------------------------
# ADR-042 (threeway-candidate-id-pair-binding-dos): cross-pair candidate_id reuse DoS,
# CLOSED structurally by PAIR-NAMESPACED candidate ids. Candidate ids are "<pair>:<local>"
# (e.g. "A:c1") and authoritative_candidate requires a candidate's DECLARED pair to equal the
# id's namespace. So a legit executing_coordinator of ANOTHER pair (coordinator2/pair-B) that
# reuses the victim's id "A:c1" must declare pair "B" (its only self-consistent pair) — but
# namespace("A:c1")=="A" != "B", so it is INELIGIBLE and ignored, in BOTH declare orders. This
# supersedes the order-dependent first-writer-wins attempt (which only MOVED the race: it closed
# attacker-declares-later but reopened attacker-declares-earlier). Mutation-proof: drop the
# `if pair != ns` clause in authoritative_candidate and the attacker-earlier test goes RED.
# ---------------------------------------------------------------------------

def _register_coordinator2(reg, ks, privs):
    """Register pair-B's executing coordinator as a fully-legit insider seat (registry + keystore)."""
    from threeway import keys
    c2_priv, c2_pub = keys.generate_keypair()
    (reg / "coordinator2.pub").write_text(c2_pub + "\n")
    (ks / "coordinator2.ed25519").write_text(keys.private_to_hex(c2_priv) + "\n")
    privs["coordinator2"] = c2_priv


def _cross_pair_attacker_events():
    """The overseer's LEGIT pair-B assignment + coordinator2's cross-pair shadow reusing the
    victim's id 'A:c1' while declaring pair 'B' (its only self-consistent pair). Returns (assign_b,
    shadow_b) as UNSIGNED events; the caller appends them (in whichever order) with the right keys."""
    from threeway.policy import default_policy
    from threeway.envelope import Event
    assign_b = Event(id="assignment-overseer-B", seq=0, bus_id="prod",
                     schema_version="threeway/1", kind="assignment", sender="overseer",
                     recipient="all", signer="overseer:mech:s1",
                     payload={"pair": "B", "builder": "director2",
                              "builder_provider": "claude",
                              "primary_verifier": "operator2",
                              "primary_verifier_provider": "codex",
                              "executing_coordinator": "coordinator2"},
                     candidate_id="A:c1")
    shadow_b = Event(id="candidate-coordinator2-Ac1", seq=0, bus_id="prod",
                     schema_version="threeway/1", kind="candidate", sender="coordinator2",
                     recipient="all", signer="coordinator2:codex:s1",
                     payload={"pair": "B", "staging_base_sha": "a" * 40,
                              "branch_sha": "b" * 40, "integration_sha": "c" * 40,
                              "risk_tier_claimed": "T1",
                              "policy_digest": default_policy().policy_digest()},
                     candidate_id="A:c1", subject_sha="c" * 40)
    return assign_b, shadow_b


def test_cross_pair_namespace_blocks_reuse_attacker_declares_later(live_repo, seatkit):
    # Victim seeds a complete, signed pair-A promotion for "A:c1" FIRST; the legit pair-B coordinator
    # then reuses "A:c1" declaring pair "B" at a HIGHER seq. namespace("A:c1")=="A" != declared "B",
    # so the shadow is ineligible -> victim stays authoritative and COMPLETES. (This case the prior
    # first-writer-wins fix also closed; kept to pin the namespace path for the later-declare order.)
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    _register_coordinator2(reg, ks, privs)
    store = EventStore(r / "coordination" / "threeway" / "events")
    base_sha, branch_sha, integ = _seed_valid(store, r, privs)   # victim first (lower seq)
    assign_b, shadow_b = _cross_pair_attacker_events()
    store.append(assign_b, privs["overseer"])
    store.append(shadow_b, privs["coordinator2"])                # attacker LATER (higher seq)

    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ


def test_cross_pair_namespace_blocks_reuse_attacker_declares_earlier(live_repo, seatkit):
    # The order first-writer-wins FAILED: the legit pair-B coordinator reuses "A:c1" declaring pair
    # "B" BEFORE the victim ever declares (lower seq). Namespacing is order-INDEPENDENT: the shadow's
    # declared "B" != namespace("A:c1")=="A", so it is ineligible regardless of seq, the victim's
    # later pair-A promotion stays authoritative, and "A:c1" COMPLETES. main never sits at the
    # attacker's bogus SHA. This is the test that proves the cross-pair DoS CLASS is closed.
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    _register_coordinator2(reg, ks, privs)
    store = EventStore(r / "coordination" / "threeway" / "events")
    assign_b, shadow_b = _cross_pair_attacker_events()
    store.append(assign_b, privs["overseer"])
    store.append(shadow_b, privs["coordinator2"])                # attacker FIRST (lower seq)
    base_sha, branch_sha, integ = _seed_valid(store, r, privs)   # victim LATER (higher seq)

    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ
    # the gate moved main to the VICTIM's integration_sha, never the attacker's bogus "c"*40.
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() != "c" * 40


# ---------------------------------------------------------------------------
# ADR-041 (Rule #13, 5th-layer brick): verify_and_reduce dereferences id (.startswith),
# signer (_seat split) and signature_version (set membership) at the TOP of its
# load-bearing block — and that runs at run_gate STEP 1, OUTSIDE run_gate's try, BEFORE
# reduce()'s type filter. A non-str id/signer or unhashable signature_version raises
# UNCAUGHT there (AttributeError / TypeError) -> a TOTAL-BUS brick: ONE planted event
# crashes run_gate for EVERY candidate, including a fully-legit independent one. `signer`
# is UNSIGNED (not in the 14-field signed view), so an insider can validly sign an event
# as itself and overwrite signer freely while the signature still verifies. The fix DROPS
# such a malformed event up-front; the legit merge COMPLETES and the bus stays total.
#
# Plant pattern: append the poison with valid str fields (so store.append signs + names
# the file), then rewrite the AT-REST JSON's target field to a list. from_json_obj does no
# type validation, so all_events() yields the malformed in-memory Event; for signer the
# signature still verifies (signer is excluded from signed_bytes).
# ---------------------------------------------------------------------------

import json as _json


def _poison_atrest_field(store, ev_id, field, value):
    """Rewrite one field of an already-appended event's at-rest JSON to `value`.

    Returns nothing; all_events() will subsequently yield the malformed Event
    (from_json_obj does no type validation)."""
    import pathlib
    hits = list(pathlib.Path(store._dir).glob(f"*-{ev_id}.json"))
    assert len(hits) == 1, f"expected exactly one stored event for id {ev_id!r}, found {hits}"
    obj = _json.loads(hits[0].read_text())
    obj[field] = value
    hits[0].write_text(_json.dumps(obj, indent=2, ensure_ascii=False))


def test_run_gate_total_under_nonstr_signer(live_repo, seatkit):
    # `signer` is UNSIGNED (excluded from the 14-field signed view, envelope.py:67). An insider
    # validly signs a load-bearing co_sign as its own registered seat, then sets signer to a LIST.
    # The signature STILL verifies (signer is not in signed_bytes), but verify_and_reduce's
    # _seat(ev.signer) -> ev.signer.split(":", 1) raises AttributeError UNCAUGHT at run_gate step 1
    # (OUTSIDE its try) -> total-bus brick. The ADR-041 up-front type-safety drop fixes it.
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    _, _, integ = _seed_valid(store, r, privs)   # complete, signed, legit T1 promotion for c1
    from threeway.envelope import Event
    poison = Event(id="cosign-nonstr-signer-c1", seq=0, bus_id="prod",
                   schema_version="threeway/1", kind="co_sign", sender="operator",
                   recipient="all", signer="operator:claude:s1",
                   payload={"verdict": "GO"}, candidate_id="A:c1", subject_sha=integ)
    store.append(poison, privs["operator"])   # validly self-signed by registered operator seat
    # AFTER signing, overwrite the at-rest signer with a LIST (signer is unsigned -> still verifies).
    _poison_atrest_field(store, "cosign-nonstr-signer-c1", "signer", ["operator", "claude", "s1"])

    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason   # did NOT raise; poison dropped, legit merge ran
    # main moved to the legit integration_sha — the list-signer poison could not brick the merge.
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ
    # the malformed co_sign is ABSENT from effective state; the legit completion fact is present.
    from threeway.gate import verify_and_reduce
    state = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
    assert state.merge_completed("A:c1") is not None


def test_run_gate_total_under_nonstr_signer_not_bricking_other_candidate(live_repo, seatkit):
    # TOTAL-BUS property: the list-signer poison must not brick run_gate for an UNRELATED candidate.
    # We run_gate a candidate id that has no events ("c2"): pre-fix verify_and_reduce raises
    # AttributeError on the poison BEFORE c2 is even evaluated -> c2's gate crashes too. Post-fix the
    # poison is dropped and c2 returns a clean PENDING (no events -> not mergeable), never a crash.
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    _, _, integ = _seed_valid(store, r, privs)   # legit promotion for c1 (unrelated to c2)
    from threeway.envelope import Event
    poison = Event(id="cosign-nonstr-signer-c2brick", seq=0, bus_id="prod",
                   schema_version="threeway/1", kind="co_sign", sender="operator",
                   recipient="all", signer="operator:claude:s1",
                   payload={"verdict": "GO"}, candidate_id="A:c1", subject_sha=integ)
    store.append(poison, privs["operator"])
    _poison_atrest_field(store, "cosign-nonstr-signer-c2brick", "signer", ["operator", "claude", "s1"])

    # an entirely independent candidate c2 (no events) must NOT be bricked by the c1-area poison.
    res = run_gate("c2", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome in ("PENDING", "REJECTED"), res.reason   # did NOT raise; total bus holds
    # c1's main ref is untouched by the c2 gate run.
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == base


def test_run_gate_total_under_nonstr_id(live_repo, seatkit):
    # A non-str `id` (a LIST) makes verify_and_reduce's ev.id.startswith(RESERVED_COMPLETION_PREFIX)
    # raise AttributeError UNCAUGHT at run_gate step 1 (OUTSIDE its try) -> total-bus brick. The
    # ADR-041 up-front drop fixes it. (id is signed, but no forgery is needed: an insider can sign a
    # str id then rewrite the at-rest JSON; from_json_obj does no type validation, so this is the
    # same insider-controlled at-rest vector the stores do not guard.)
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    _, _, integ = _seed_valid(store, r, privs)
    from threeway.envelope import Event
    poison = Event(id="cosign-nonstr-id-c1", seq=0, bus_id="prod",
                   schema_version="threeway/1", kind="co_sign", sender="operator",
                   recipient="all", signer="operator:claude:s1",
                   payload={"verdict": "GO"}, candidate_id="A:c1", subject_sha=integ)
    store.append(poison, privs["operator"])   # appended with a valid str id (file is named after it)
    _poison_atrest_field(store, "cosign-nonstr-id-c1", "id", ["not", "a", "string"])

    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason   # did NOT raise; poison dropped, legit merge ran
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ
    from threeway.gate import verify_and_reduce
    state = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
    assert state.merge_completed("A:c1") is not None


# ---------------------------------------------------------------------------
# Task-10 (ADR-041, comprehensive well_formed): a 6th total-bus brick. The
# `kind in LOAD_BEARING_KINDS` SET-MEMBERSHIP test (gate.py AND reducer.py) GATES ENTRY to
# the block holding every isinstance guard, so an UNHASHABLE list/dict `kind` raises
# TypeError FIRST — BEFORE any per-field check can run. Prior per-field guards (id/signer/
# signature_version) lived INSIDE that block, unreachable when kind itself is unhashable.
# The well_formed envelope check (applied to EVERY event up front) covers kind too.
# ---------------------------------------------------------------------------

def test_run_gate_total_under_unhashable_kind(live_repo, seatkit):
    # An UNHASHABLE `kind` (a LIST) makes `ev.kind in LOAD_BEARING_KINDS` raise
    # TypeError: unhashable type: 'list' UNCAUGHT — and that test GATES ENTRY to the
    # load-bearing block, so it bricks FIRST, before any per-field isinstance guard runs.
    # Plant the same at-rest way the nonstr-id/signer tests do: append a valid str-kind event
    # (so store.append signs + names the file), then rewrite the at-rest JSON's kind to a list;
    # from_json_obj does no type validation, so all_events() yields the malformed Event.
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    _, _, integ = _seed_valid(store, r, privs)   # complete, signed, legit T1 promotion for c1
    from threeway.envelope import Event
    poison = Event(id="cosign-listkind-c1", seq=0, bus_id="prod",
                   schema_version="threeway/1", kind="co_sign", sender="operator",
                   recipient="all", signer="operator:claude:s1",
                   payload={"verdict": "GO"}, candidate_id="A:c1", subject_sha=integ)
    store.append(poison, privs["operator"])   # validly self-signed by registered operator seat
    # AFTER signing, overwrite the at-rest kind with a LIST (kind IS signed, but the at-rest JSON
    # is insider-controlled and from_json_obj does no type validation; the well_formed drop fixes
    # it regardless of whether the signature would still verify).
    _poison_atrest_field(store, "cosign-listkind-c1", "kind", ["co", "sign"])

    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason   # did NOT raise; poison dropped, legit merge ran
    # main moved to the legit integration_sha — the list-kind poison could not brick the merge.
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ
    from threeway.gate import verify_and_reduce
    state = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
    assert state.merge_completed("A:c1") is not None


def test_run_gate_total_under_unhashable_kind_not_bricking_other_candidate(live_repo, seatkit):
    # TOTAL-BUS property: the list-kind poison must not brick run_gate for an UNRELATED candidate.
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    _, _, integ = _seed_valid(store, r, privs)
    from threeway.envelope import Event
    poison = Event(id="cosign-listkind-c2brick", seq=0, bus_id="prod",
                   schema_version="threeway/1", kind="co_sign", sender="operator",
                   recipient="all", signer="operator:claude:s1",
                   payload={"verdict": "GO"}, candidate_id="A:c1", subject_sha=integ)
    store.append(poison, privs["operator"])
    _poison_atrest_field(store, "cosign-listkind-c2brick", "kind", ["co", "sign"])

    res = run_gate("c2", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome in ("PENDING", "REJECTED"), res.reason   # did NOT raise; total bus holds
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == base


def test_run_gate_total_under_unhashable_signature_version(live_repo, seatkit):
    # An unhashable `signature_version` (a LIST) makes verify_and_reduce's
    # `ev.signature_version not in _ACCEPTED_SIG_VERSIONS` (a set membership test) raise
    # TypeError: unhashable type: 'list' UNCAUGHT at run_gate step 1 (OUTSIDE its try) -> total-bus
    # brick. signature_version IS signed, but the at-rest JSON is insider-controlled and from_json_obj
    # does no type validation; the ADR-041 up-front drop fixes it regardless of signature validity.
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    _, _, integ = _seed_valid(store, r, privs)
    from threeway.envelope import Event
    poison = Event(id="cosign-listsigver-c1", seq=0, bus_id="prod",
                   schema_version="threeway/1", kind="co_sign", sender="operator",
                   recipient="all", signer="operator:claude:s1",
                   payload={"verdict": "GO"}, candidate_id="A:c1", subject_sha=integ)
    store.append(poison, privs["operator"])
    _poison_atrest_field(store, "cosign-listsigver-c1", "signature_version", ["threeway-sign/2"])

    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason   # did NOT raise; poison dropped, legit merge ran
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ
    from threeway.gate import verify_and_reduce
    state = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
    assert state.merge_completed("A:c1") is not None


# ---------------------------------------------------------------------------
# ADR-043 end-to-end: full T3 promotion through the SIGNATURE-VERIFYING gate.
# The tier/predicate unit suites use the no-signature reduce() path; these drive
# the real verify_and_reduce so the chief-key registry requirement is exercised.
# ---------------------------------------------------------------------------
@pytest.fixture()
def live_repo_t3(tmp_path):
    """Like live_repo but the builder branch touches a T3 path (coordination/threeway/keys/),
    so the gate-computed effective tier is T3 — exercising the ADR-043 freshness + per-approver
    clauses on the real signed path."""
    r = tmp_path / "repo"; r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@e.st"); _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "base")
    base = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", "refs/threeway/test-main", base)
    _git(r, "checkout", "-q", "-b", "feat")
    (r / "coordination" / "threeway" / "keys").mkdir(parents=True)
    (r / "coordination" / "threeway" / "keys" / "newseat.pub").write_text("deadbeef\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "feat-t3")
    branch = _git(r, "rev-parse", "HEAD").stdout.strip()
    return r, base, branch


_T3_NONCE = "ovr-nonce-gate"


def _ev3(kind, sender, signer, payload, *, eid, subject_sha=None):
    from threeway.envelope import Event
    return Event(id=eid, seq=0, bus_id="prod", schema_version="threeway/1", kind=kind,
                 sender=sender, recipient="all", signer=signer, payload=payload,
                 candidate_id="A:c1", brief_id="b1", brief_version=1, subject_sha=subject_sha)


def _seed_full_t3(r, base, branch, integ, privs):
    """Append a complete, correctly-signed T3 promotion for A:c1: the base set (T3 brief/cycle_go,
    allowed under coordination/threeway/keys/) + mirror co_sign + re_verify echoing the overseer
    freshness nonce + overseer re_verify_challenge + overseer approver_roster + two chief
    human_approvals signed by distinct key-bound chief seats. Returns the EventStore."""
    from threeway.loop import build_candidate_events, PAIR_A
    store = EventStore(r / "coordination" / "threeway" / "events")
    base_set = build_candidate_events(base, branch, integ, privs, tier="T3",
                                      allowed_paths=("coordination/threeway/keys/",), pair=PAIR_A)
    extra = [
        _ev3("assignment", "overseer", "overseer:mech:s1",
             {"pair": "B", "builder": "director2", "builder_provider": "claude",
              "primary_verifier": "operator2", "primary_verifier_provider": "codex",
              "executing_coordinator": "coordinator2"}, eid="assignment-overseer-Bmirror"),
        _ev3("co_sign", "operator2", "operator2:codex:s1", {"verdict": "GO"},
             eid="co_sign-operator2-A:c1", subject_sha=integ),
        _ev3("re_verify", "operator", "operator:claude:s2",
             {"verdict": "GO", "challenge_nonce": _T3_NONCE},
             eid="re_verify-operator-A:c1", subject_sha=integ),
        _ev3("re_verify_challenge", "overseer", "overseer:mech:s1", {"nonce": _T3_NONCE},
             eid="re_verify_challenge-overseer-A:c1", subject_sha=integ),
        _ev3("approver_roster", "overseer", "overseer:mech:s1",
             {"approvers": ["chief-gemini", "chief-chatgpt"]}, eid="approver_roster-overseer-A:c1"),
        _ev3("human_approval", "chief-gemini", "chief-gemini:relay:s1",
             {"approver_identity": "chief-gemini", "integration_sha": integ, "decision": "approve"},
             eid="human_approval-chief-gemini-A:c1"),
        _ev3("human_approval", "chief-chatgpt", "chief-chatgpt:relay:s1",
             {"approver_identity": "chief-chatgpt", "integration_sha": integ, "decision": "approve"},
             eid="human_approval-chief-chatgpt-A:c1"),
    ]
    for ev in list(base_set) + extra:
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    return store


def test_run_gate_completes_full_t3_through_signed_gate(live_repo_t3, seatkit):
    from threeway import gitcas
    r, base, branch = live_repo_t3
    reg, ks, privs = seatkit
    tree, clean = gitcas.merge_tree(r, base, branch)
    assert clean
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge A:c1")
    store = _seed_full_t3(r, base, branch, integ, privs)
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ


def test_run_gate_t3_pending_when_chief_keys_unregistered(live_repo_t3, seatkit):
    # ADR-043 operational precondition (re-cert MAJOR): the chief approver seats must have their
    # OWN registry keys, or verify_and_reduce DROPS their human_approvals as unknown-seat (ADR-040)
    # and the T3 candidate is stuck PENDING — fail-CLOSED (never a wrong promotion), but a real
    # liveness requirement. Removing the chief pubs from the registry keeps it PENDING.
    from threeway import gitcas
    r, base, branch = live_repo_t3
    reg, ks, privs = seatkit
    tree, clean = gitcas.merge_tree(r, base, branch)
    assert clean
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge A:c1")
    store = _seed_full_t3(r, base, branch, integ, privs)
    (reg / "chief-gemini.pub").unlink()
    (reg / "chief-chatgpt.pub").unlink()
    res = run_gate("A:c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "PENDING", res.reason
    assert "co_sign not satisfied" in res.reason
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == base
