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


def test_verify_and_reduce_drops_unsigned_event(seatkit, tmp_path):
    # ADR-040: a load-bearing event with a missing/invalid signature is DROPPED (not raised),
    # so the fact it would have carried is ABSENT from effective state. Dropping is fail-safe:
    # an unsigned event has no authority, so this can only REMOVE it, never admit a forged fact.
    reg, ks, privs = seatkit
    from threeway.envelope import Event
    ev = Event(id="e1", seq=1, bus_id="prod", schema_version="threeway/1",
               kind="candidate", sender="coordinator", recipient="all",
               signer="coordinator:claude:s1", payload={"pair": "A"}, candidate_id="c1")
    # not signed -> dropped at the signature check; no raise.
    state = verify_and_reduce([ev], registry_dir=reg, bus_id="prod")
    assert state.candidate("c1") is None   # the unsigned candidate never entered effective state


def test_verify_and_reduce_drops_bus_id_mismatch_replay(seatkit, tmp_path):
    # ADR-040: a load-bearing event from the WRONG bus (replay) is DROPPED, not raised — one
    # forged wrong-bus event must not brick verify_and_reduce for every candidate. The fact is absent.
    reg, ks, privs = seatkit
    from threeway.envelope import Event, sign_event
    ev = Event(id="e1", seq=1, bus_id="TEST-BUS", schema_version="threeway/1",
               kind="candidate", sender="coordinator", recipient="all",
               signer="coordinator:claude:s1", payload={"pair": "A"}, candidate_id="c1")
    sign_event(ev, privs["coordinator"])
    state = verify_and_reduce([ev], registry_dir=reg, bus_id="prod")
    assert state.candidate("c1") is None   # wrong-bus replay dropped; never reduced


def test_verify_and_reduce_drops_unknown_signer_seat(seatkit, tmp_path):
    # ADR-040: a load-bearing event signed by an UNKNOWN seat (no registry key) is DROPPED, not
    # raised. An unknown seat has no authority, so the fact is simply absent.
    reg, ks, privs = seatkit
    from threeway.envelope import Event, sign_event
    ev = Event(id="e1", seq=1, bus_id="prod", schema_version="threeway/1",
               kind="candidate", sender="ghost", recipient="all",
               signer="ghost:claude:s1", payload={"pair": "A"}, candidate_id="c1")
    sign_event(ev, privs["coordinator"])  # signed by coordinator's key but claims ghost
    state = verify_and_reduce([ev], registry_dir=reg, bus_id="prod")
    assert state.candidate("c1") is None   # unknown-seat event dropped; never reduced


def test_gate_drops_unknown_signature_version(seatkit, tmp_path):
    # ADR-040: a load-bearing event presenting an UNACCEPTED signature_version is DROPPED, not
    # raised. The fact is absent (a weaker/forged profile has no authority).
    reg, ks, privs = seatkit
    from threeway.envelope import Event, sign_event
    ev = Event(id="e1", seq=1, bus_id="prod", schema_version="threeway/1",
               kind="candidate", sender="coordinator", recipient="all",
               signer="coordinator:claude:s1", payload={"pair": "A"}, candidate_id="c1",
               signature_version="threeway-sign/1")   # unaccepted signature profile
    sign_event(ev, privs["coordinator"])               # validly signed under the old profile
    state = verify_and_reduce([ev], registry_dir=reg, bus_id="prod")
    assert state.candidate("c1") is None   # unaccepted-profile event dropped; never reduced


def test_verify_and_reduce_accepts_valid_signed_events(seatkit, tmp_path):
    reg, ks, privs = seatkit
    from threeway.envelope import Event, sign_event
    ev = Event(id="e1", seq=1, bus_id="prod", schema_version="threeway/1",
               kind="candidate", sender="coordinator", recipient="all",
               signer="coordinator:claude:s1", payload={"pair": "A"}, candidate_id="c1")
    sign_event(ev, privs["coordinator"])
    state = verify_and_reduce([ev], registry_dir=reg, bus_id="prod")
    assert state.candidate("c1") is not None


def test_verify_and_reduce_rejects_duplicate_event_id(seatkit, tmp_path):
    # ADR-037: event id is signed but NOT globally unique; a duplicate id across the
    # load-bearing set is a collision/replay (an insider re-using a victim fact's id to
    # shadow it) and must fail closed.
    reg, ks, privs = seatkit
    from threeway.envelope import Event, sign_event
    victim = Event(id="DUP", seq=1, bus_id="prod", schema_version="threeway/1",
                   kind="co_sign", sender="operator", recipient="all",
                   signer="operator:claude:s1", payload={"verdict": "GO"},
                   candidate_id="c1", subject_sha="2" * 40)
    sign_event(victim, privs["operator"])
    decoy = Event(id="DUP", seq=2, bus_id="prod", schema_version="threeway/1",
                  kind="attestation", sender="director", recipient="all",
                  signer="director:claude:s1", payload={"kind": "release", "verdict": "GO"},
                  candidate_id="c1", subject_sha="2" * 40)
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
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge c1")
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
                   candidate_id="c1", subject_sha="c" * 40)
    store.append(shadow, privs["operator"])
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason
    # main moved to the AUTHORITATIVE integration_sha, never the shadow's "c"*40.
    new_head = _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip()
    assert new_head == integ
    assert new_head != "c" * 40


def test_run_gate_survives_poisoned_reserved_merge_id(live_repo, seatkit):
    # ADR-039 availability win (supersedes the old ADR-037 reserved-id REJECT): an insider
    # pre-claims the predictable completion id 'merge-c1' (here a forged co_sign). The OLD
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
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge c1")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    from threeway.envelope import Event
    poison = Event(id="merge-c1", seq=0, bus_id="prod", schema_version="threeway/1",
                   kind="co_sign", sender="operator", recipient="all",
                   signer="operator:claude:s1", payload={"verdict": "GO"},
                   candidate_id="c1", subject_sha=integ)
    store.append(poison, privs["operator"])
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
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
    # EVERY candidate). Here a forged co_sign GO with id 'merge-c1' from operator must NOT surface
    # as a co_sign in effective state. (Mutation check: without the drop, state.co_sign would
    # return it, since each event is validly self-signed.)
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    from threeway import gitcas
    tree, clean = gitcas.merge_tree(r, base, branch)
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge c1")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    from threeway.envelope import Event
    smuggled = Event(id="merge-c1", seq=0, bus_id="prod", schema_version="threeway/1",
                     kind="co_sign", sender="operator", recipient="all",
                     signer="operator:claude:s1", payload={"verdict": "GO"},
                     candidate_id="c1", subject_sha=integ)
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
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge c1")
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

    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
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
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge c1")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    r1 = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                  main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert r1.outcome == "COMPLETED", r1.reason
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ

    # withhold the recorded fact: delete the merge_completed event file (post-CAS-fail simulation).
    import pathlib
    removed = 0
    for p in pathlib.Path(events_dir).glob("*-merge-c1.json"):
        p.unlink(); removed += 1
    assert removed == 1, "expected exactly one merge_completed fact to withhold"
    # sanity: the fact is now gone from effective state.
    state = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
    assert state.merge_completed("c1") is None

    # re-run: no fact, but main==integ -> COMPLETED via main-state idempotency, not a stale REJECT.
    r2 = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                  main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert r2.outcome == "COMPLETED", r2.reason
    assert "idempotent" in r2.reason


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
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge c1")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])

    r1 = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                  main_ref="refs/threeway/test-main", gate_seat="custom-gate")
    assert r1.outcome == "COMPLETED", r1.reason

    # crash-recovery re-run: the gate's own custom-gate-signed merge_completed fact must be
    # HONORED by the reducer -> a clean idempotent no-op, NOT a reserved-id REJECT.
    r2 = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
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
    assert honored.merge_completed("c1") is not None
    dropped = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
    assert dropped.merge_completed("c1") is None


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

def _seed_valid(store, r, privs, candidate_id="c1"):
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
                   payload={"verdict": "GO"}, candidate_id="c1", subject_sha=integ)
    store.append(poison, privs["operator"])
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
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
                   payload={"verdict": "GO"}, candidate_id="c1", subject_sha=integ)
    store.append(poison, privs["operator"])
    r1 = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                  main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert r1.outcome == "COMPLETED", r1.reason
    # the poison is STILL on the bus; a re-run must not raise (totality holds per-invocation).
    r2 = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
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
                   payload={"verdict": "GO"}, candidate_id="c1", subject_sha=integ)
    store.append(poison, privs["operator"])   # signed with a REGISTERED key but claims 'ghost'
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
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
                   payload={"verdict": "GO"}, candidate_id="c1", subject_sha=integ,
                   signature_version="threeway-sign/1")
    store.append(poison, privs["operator"])   # validly signed under the old (unaccepted) profile
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
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
                      candidate_id="c1", subject_sha=integ)   # NO staging_base_sha
    store.append(malformed, privs["coordinator"])
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
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
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason   # did NOT raise; poison dropped, legit merge ran
    # main moved to the legit integration_sha — the poison could not brick the merge (total bus).
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ
    # the poison co_sign is ABSENT from effective state (dropped, never reduced); the legit
    # state is intact (verify_and_reduce did not raise on the unhashable keyed field).
    from threeway.gate import verify_and_reduce
    state = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
    assert state.merge_completed("c1") is not None


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
                   candidate_id="c1", subject_sha="c" * 40)
    store.append(poison, privs["operator"])
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
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
                   candidate_id="c1", subject_sha="c" * 40)
    store.append(poison, privs["operator"])
    state = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
    auth = state.authoritative_candidate("c1")   # must NOT raise TypeError
    assert auth is not None
    # the legit (coordinator-signed, str-pair) candidate is authoritative, never the list-pair poison.
    assert auth.payload.get("pair") == "A"
    assert auth.signer.split(":", 1)[0] == "coordinator"


# ---------------------------------------------------------------------------
# Residual (i): cross-pair candidate_id reuse DoS — confirmed-but-deferred,
# pinned strict-xfail so CI tracks it until the candidate_id<->pair-binding
# slice lands. This is a REAL reproducing scenario, not a vacuous pin.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="threeway-candidate-id-pair-binding-dos residual (i): "
                   "a legit executing_coordinator of another overseer-assigned pair can reuse a "
                   "candidate_id declaring its own pair (higher seq) to capture authoritative_candidate "
                   "and stall the victim's merge at PENDING — availability-only, never promotes; "
                   "scoped to a follow-up candidate_id<->pair-binding slice")
def test_cross_pair_candidate_id_reuse_dos_residual(live_repo, seatkit):
    # Victim: a complete, signed T1 promotion for candidate_id "c1" on pair A (executing
    # coordinator = 'coordinator'). Attacker: the OVERSEER legitimately assigns pair B to a
    # different executing coordinator ('coordinator2'); that coordinator then appends a
    # candidate REUSING id-space for the SAME candidate_id "c1" but declaring pair "B",
    # at a HIGHER seq. authoritative_candidate("c1") iterates highest-seq-first and matches
    # the FIRST candidate whose signer-seat == its declared pair's executing_coordinator —
    # the pair-B shadow qualifies (coordinator2 signs it, pair-B assignment names coordinator2),
    # so it CAPTURES authority. Its base/branch don't satisfy the victim's evaluate() clauses,
    # so c1 stalls at non-COMPLETED. Availability-only: the shadow can never PROMOTE (the gate
    # recomputes the merge from the shadow's own SHAs and the victim's attestations won't bind),
    # but it can stall the victim. The xpass condition (asserted below) is that c1 COMPLETES;
    # today it does NOT (the shadow captured authority) -> XFAILs now, XPASSes when the binding fix
    # makes a candidate_id bind to the pair of its FIRST/authoritative declaration.
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    # register pair-B's executing coordinator ('coordinator2') in both stores so its candidate
    # both verifies (registry) and signs (keystore) like any legit insider seat.
    from threeway import keys
    c2_priv, c2_pub = keys.generate_keypair()
    (reg / "coordinator2.pub").write_text(c2_pub + "\n")
    (ks / "coordinator2.ed25519").write_text(keys.private_to_hex(c2_priv) + "\n")
    privs["coordinator2"] = c2_priv

    store = EventStore(r / "coordination" / "threeway" / "events")
    base_sha, branch_sha, integ = _seed_valid(store, r, privs)

    from threeway.policy import default_policy
    from threeway.envelope import Event
    # overseer LEGITIMATELY assigns pair B to coordinator2 (a real, signed assignment).
    assign_b = Event(id="assignment-overseer-B", seq=0, bus_id="prod",
                     schema_version="threeway/1", kind="assignment", sender="overseer",
                     recipient="all", signer="overseer:mech:s1",
                     payload={"pair": "B", "builder": "director2",
                              "builder_provider": "claude",
                              "primary_verifier": "operator2",
                              "primary_verifier_provider": "codex",
                              "executing_coordinator": "coordinator2"},
                     candidate_id="c1")
    store.append(assign_b, privs["overseer"])
    # coordinator2 reuses candidate_id "c1" but declares pair "B" at a higher seq -> captures
    # authoritative_candidate via the pair-B assignment it legitimately holds.
    shadow_b = Event(id="candidate-coordinator2-c1", seq=0, bus_id="prod",
                     schema_version="threeway/1", kind="candidate", sender="coordinator2",
                     recipient="all", signer="coordinator2:codex:s1",
                     payload={"pair": "B", "staging_base_sha": "a" * 40,
                              "branch_sha": "b" * 40, "integration_sha": "c" * 40,
                              "risk_tier_claimed": "T1",
                              "policy_digest": default_policy().policy_digest()},
                     candidate_id="c1", subject_sha="c" * 40)
    store.append(shadow_b, privs["coordinator2"])

    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    # XPASS-when-fixed condition: the victim's legit promotion COMPLETES despite the cross-pair
    # shadow. TODAY the shadow captured authority -> c1 does NOT complete (stalled), so this
    # assertion FAILS -> the test XFAILs. When candidate_id<->pair binding lands, the pair-A
    # candidate stays authoritative and c1 COMPLETES -> XPASS (strict -> flips this pin RED to
    # signal the fix landed and the xfail must be removed).
    assert res.outcome == "COMPLETED", res.reason
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ
