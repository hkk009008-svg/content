"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_activation_scripts.py -q

Pins for the threeway ACTIVATION TOOLING scripts (rewritten to the REAL envelope/gate/cutover API).
The original codex/agy drafts used a fabricated schema (ev.event_type / ev.subject /
Event(event_type=...)) and crashed on first use; these lock the corrected shapes against the live
reducer/gate (non-vacuous: a wrong bus_id / signer-seat / field makes verify_and_reduce DROP the
event, so the state assertions go RED).
"""
import os
import subprocess

import pytest

from threeway import gitcas, keys
from threeway.gate import verify_and_reduce
from threeway.policy import default_policy
from threeway.store import EventStore


def _env():
    e = dict(os.environ); e.pop("GIT_INDEX_FILE", None); return e


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True,
                          capture_output=True, text=True, env=_env())


@pytest.fixture()
def seatkit(tmp_path, monkeypatch):
    reg = tmp_path / "pub"; ks = tmp_path / "ks"; reg.mkdir(); ks.mkdir()
    privs = {}
    for seat in ("director", "operator", "operator2", "coordinator", "overseer", "ci",
                 "merge-gate", "chief-gemini", "chief-chatgpt"):
        priv, pub = keys.generate_keypair()
        (reg / f"{seat}.pub").write_text(pub + "\n")
        (ks / f"{seat}.ed25519").write_text(keys.private_to_hex(priv) + "\n")
        privs[seat] = priv
    monkeypatch.setenv("THREEWAY_KEYSTORE", str(ks))
    return reg, ks, privs


@pytest.fixture()
def live_repo(tmp_path):
    r = tmp_path / "repo"; r.mkdir()
    _git(r, "init", "-q"); _git(r, "config", "user.email", "t@e.st"); _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n"); _git(r, "add", "-A"); _git(r, "commit", "-qm", "base")
    base = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", "refs/threeway/test-main", base)
    _git(r, "checkout", "-q", "-b", "feat")
    (r / "cinema").mkdir(); (r / "cinema" / "foo.py").write_text("x = 1\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "feat")
    branch = _git(r, "rev-parse", "HEAD").stdout.strip()
    return r, base, branch


# --------------------------------------------------------------------------- sign_ci_result
def test_sign_ci_result_emits_a_reducible_pass_for_the_sha(seatkit, tmp_path):
    from scripts.sign_ci_result import emit_ci_result
    reg, ks, privs = seatkit
    store = EventStore(tmp_path / "events")
    sha = "a" * 40
    ev = emit_ci_result(store, sha, "PASS", privs["ci"])
    # correct envelope: kind, bus, subject_sha=integration_sha, signer seat 'ci'
    assert ev.kind == "ci_result"
    assert ev.bus_id == "prod"
    assert ev.subject_sha == sha
    assert ev.signer.split(":", 1)[0] == "ci"
    # NON-VACUITY: the reducer accepts it ONLY if every signed field is right -> the gate sees PASS
    state = verify_and_reduce(list(store.iter_events()), registry_dir=reg, bus_id="prod")
    ci = state.ci_result(sha)
    assert ci is not None, "ci_result was dropped by the reducer (wrong bus/signer/field)"
    assert ci.payload["result"] == "PASS"
    assert ci.payload["policy_digest"] == default_policy().policy_digest()


# --------------------------------------------------------------------------- run_merge_gate
def test_run_merge_gate_poll_once_merges_a_complete_candidate(seatkit, live_repo):
    from scripts.run_merge_gate import poll_once
    from threeway.loop import build_candidate_events
    reg, ks, privs = seatkit
    r, base, branch = live_repo
    store = EventStore(r / "coordination" / "threeway" / "events")
    tree, clean = gitcas.merge_tree(r, base, branch); assert clean
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge A:c1")
    for ev in build_candidate_events(base, branch, integ, privs):   # default candidate_id -> "A:c1"
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    results = poll_once(store, repo=r, registry_dir=reg, bus_id="prod",
                        main_ref="refs/threeway/test-main")
    outcomes = {cid: res.outcome for cid, res in results}
    assert outcomes.get("A:c1") == "COMPLETED", outcomes
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ


# --------------------------------------------------------------------------- agy_observer
def test_agy_observer_summarize_uses_real_fields(seatkit, tmp_path):
    from scripts.agy_observer import summarize
    from threeway.loop import build_candidate_events
    reg, ks, privs = seatkit
    # a minimal real bus: a full candidate event set (incl. a ci_result) on a file store
    store = EventStore(tmp_path / "events")
    integ = "b" * 40
    for ev in build_candidate_events("c" * 40, "d" * 40, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    summary = summarize(store)
    assert summary["total_events"] >= 1
    assert "A:c1" in summary["candidates"]                 # keyed by candidate_id (not ev.subject)
    assert summary["ci_results"].get(integ) == "PASS"      # ci_result keyed by subject_sha


# --------------------------------------------------------------------------- cutover CLI
_NAMES = [
    "2026-06-17T19-55-31Z-operator-to-director-status.md",
    "2026-06-17T20-00-00Z-director-to-operator-decision.md",
    "2026-06-17T20-00-00Z-coordinator-to-all-fyi.md",
]


def _seed_coord(root):
    sent = root / "coordination" / "mailbox" / "sent"; sent.mkdir(parents=True)
    seen = root / "coordination" / "mailbox" / "seen"; seen.mkdir(parents=True)
    for n in _NAMES:
        (sent / n).write_text("# subj\n\n**When:** " + n[:11] + n[11:20].replace("-", ":") + "\n\nbody\n")
    for s in ("director", "director2", "operator", "operator2", "coordinator", "coordinator2"):
        (seen / f"{s}.txt").write_text("2026-06-17T20:00:00Z\n")
    return root


def _new_repo(tmp_path):
    r = tmp_path / "repo"; r.mkdir()
    _git(r, "init", "-q"); _git(r, "config", "user.email", "t@e.st"); _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n"); _git(r, "add", "-A"); _git(r, "commit", "-qm", "base")
    return r


def test_cutover_cli_refuses_without_yes_then_runs_with_yes(tmp_path):
    from threeway import cutover
    r = _new_repo(tmp_path); _seed_coord(r)

    # without --yes: REFUSE (irreversible) and write NO bus
    rc = cutover.main(["--repo", str(r), "--coord-root", str(r)])
    assert rc != 0
    assert _git(r, "for-each-ref", "refs/threeway/").stdout.strip() == "", "bus written without confirmation!"

    # with --yes: the cutover runs and the signed bus exists
    rc = cutover.main(["--repo", str(r), "--coord-root", str(r), "--yes"])
    assert rc == 0
    assert "refs/threeway/events" in _git(r, "for-each-ref", "refs/threeway/").stdout
