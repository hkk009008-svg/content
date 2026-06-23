"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_activation_scripts.py -q

Pins for the threeway ACTIVATION TOOLING scripts (rewritten to the REAL envelope/gate/cutover API).
The original codex/agy drafts used a fabricated schema (ev.event_type / ev.subject /
Event(event_type=...)) and crashed on first use; these lock the corrected shapes against the live
reducer/gate (non-vacuous: a wrong bus_id / signer-seat / field makes verify_and_reduce DROP the
event, so the state assertions go RED).
"""
import os
from pathlib import Path
import subprocess
import sys

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


def _new_bare(path):
    _git(path.parent, "init", "--bare", "-q", str(path))
    return path


def _clone(bare, dest):
    _git(dest.parent, "clone", "-q", str(bare), str(dest))
    _git(dest, "config", "user.email", "t@e.st")
    _git(dest, "config", "user.name", "t")
    return dest


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


def test_sign_ci_result_cli_pushes_to_the_authoritative_remote_bus(seatkit, tmp_path):
    from scripts import sign_ci_result
    reg, ks, privs = seatkit
    remote = _new_bare(tmp_path / "bus.git")
    runner = _clone(remote, tmp_path / "runner")
    sha = "e" * 40

    rc = sign_ci_result.main([
        "--repo-dir", str(runner),
        "--remote", "origin",
        "--integration-sha", sha,
        "--result", "PASS",
    ])

    assert rc == 0
    viewer = _clone(remote, tmp_path / "viewer")
    from threeway.refstore import RefEventStore
    state = verify_and_reduce(RefEventStore(viewer, remote="origin").all_events(),
                              registry_dir=reg, bus_id="prod")
    assert state.ci_result(sha) is not None


def test_ci_workflow_signs_only_an_explicit_threeway_integration_sha():
    workflow = Path(".github/workflows/ci.yml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "integration_sha:" in workflow
    assert "integration_ref:" in workflow
    assert "ref: ${{ inputs.integration_ref || github.sha }}" in workflow
    assert 'test "$(git rev-parse HEAD)" = "$INTEGRATION_SHA"' in workflow
    assert "needs: [smoke, pytest-unit, tsc]" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "INTEGRATION_SHA: ${{ inputs.integration_sha }}" in workflow
    assert 'test "${#INTEGRATION_SHA}" -eq 40' in workflow
    assert 'python scripts/sign_ci_result.py --integration-sha "$INTEGRATION_SHA" --result PASS --remote origin' in workflow
    assert "--integration-sha ${{ github.sha }}" not in workflow


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


# --------------------------------------------------------- bare-subprocess invocation contract
# CI's `threeway-ci-result` job (.github/workflows/ci.yml) and the documented merge-gate /
# observer runbooks invoke these as `python scripts/X.py ...` from the repo root — no PYTHONPATH,
# no `python -m`. Running a file puts scripts/ on sys.path[0] (NOT the repo root), so a module-level
# `from threeway... import` raises ModuleNotFoundError. The in-process tests above never catch this:
# they `from scripts import X` under pytest, whose pyproject pythonpath=["."] patches the IN-PROCESS
# sys.path only — it does not reach a freshly-spawned subprocess. These pins run the scripts the way
# CI actually does, so the import-path defect is visible.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ACTIVATION_SCRIPTS = ["sign_ci_result.py", "run_merge_gate.py", "agy_observer.py",
                       "overseer_emit.py", "bootstrap_emit.py", "overseer_plan.py"]


def _bare_env():
    """A clean env for a real `python scripts/X.py`: GIT_INDEX_FILE stripped (seat-index hygiene)
    and PYTHONPATH stripped, so the script must put the repo root on sys.path ITSELF — a developer
    shell that exports PYTHONPATH=. must not mask the defect that CI (with no PYTHONPATH) would hit."""
    e = dict(os.environ)
    e.pop("GIT_INDEX_FILE", None)
    e.pop("PYTHONPATH", None)
    return e


@pytest.mark.parametrize("script", _ACTIVATION_SCRIPTS)
def test_activation_script_runs_as_a_bare_subprocess(script):
    # --help exits 0 only AFTER the module-level `from threeway... import` runs, so a missing
    # repo-root bootstrap surfaces here as ModuleNotFoundError (rc != 0).
    proc = subprocess.run(
        [sys.executable, f"scripts/{script}", "--help"],
        cwd=_REPO_ROOT, capture_output=True, text=True, env=_bare_env(),
    )
    assert "ModuleNotFoundError" not in proc.stderr, (
        f"{script} crashed on a bare `python scripts/{script}` (CI's invocation form):\n{proc.stderr}")
    assert proc.returncode == 0, f"{script} --help exited {proc.returncode}:\n{proc.stderr}"
