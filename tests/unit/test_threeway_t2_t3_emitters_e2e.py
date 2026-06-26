"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_t2_t3_emitters_e2e.py -q"""

from threeway import gitcas, keys
from threeway.envelope import Event
from threeway.gate import verify_and_reduce
from threeway.policy import default_policy
from threeway.refstore import RefEventStore
from tests.unit.test_threeway_e2e_walking_skeleton import _git, _run, live_repo, seatkit


def _emit_t2_base(reg, ks, repo, base, branch, *, emit_cosign: bool, tier: str = "T2"):
    cid = "A:c1"
    pd = default_policy().policy_digest()
    tree, clean = gitcas.merge_tree(repo, base, branch)
    assert clean
    integ = gitcas.commit_tree(repo, tree, [base, branch], f"threeway merge {cid}")
    L = ["--repo-dir", str(repo), "--remote", ""]
    B = ["--candidate-id", cid, "--pair", "A", "--tier", tier,
         "--staging-base", base, "--branch", branch, *L]
    _run("overseer_emit.py", "brief", "--candidate-id", cid, "--brief-id", "b1",
         "--assigned-tier", tier, "--allowed-paths", "cinema/", *L, repo=repo, ks=ks)
    _run("overseer_emit.py", "assignment", "--candidate-id", cid, "--pair", "A",
         "--builder", "director", "--builder-provider", "codex",
         "--primary-verifier", "operator", "--primary-verifier-provider", "claude",
         "--executing-coordinator", "coordinator", *L, repo=repo, ks=ks)
    _run("overseer_emit.py", "assignment", "--candidate-id", "B:c1", "--pair", "B",
         "--builder", "director2", "--builder-provider", "claude",
         "--primary-verifier", "operator2", "--primary-verifier-provider", "codex",
         "--executing-coordinator", "coordinator2", *L, repo=repo, ks=ks)
    _run("overseer_emit.py", "cycle_go", "--candidate-id", cid, "--brief-id", "b1",
         "--tier", tier, "--policy-digest", pd, *L, repo=repo, ks=ks)
    _run("seat_emit.py", "coordinator", "candidate", *B, repo=repo, ks=ks)
    _run("seat_emit.py", "operator", "attestation", "--phase", "preliminary", *B, repo=repo, ks=ks)
    _run("sign_ci_result.py", "--integration-sha", integ, "--result", "PASS",
         "--repo-dir", str(repo), repo=repo, ks=ks)
    _run("seat_emit.py", "operator", "attestation", "--phase", "release", *B, repo=repo, ks=ks)
    if emit_cosign:
        _run("seat_emit.py", "operator2", "co_sign", "--candidate-id", cid,
             "--registry-dir", str(reg), *L, repo=repo, ks=ks)
    _run("seat_emit.py", "coordinator", "release_requested", *B, repo=repo, ks=ks)
    _run("overseer_emit.py", "release_order", "--candidate-id", cid,
         "--integration-sha", integ, *L, repo=repo, ks=ks)
    return cid, integ


def test_t2_cli_happy_path_merges_with_mirror_cosign(seatkit, live_repo):
    reg, ks, privs = seatkit
    repo, base, branch = live_repo
    cid, integ = _emit_t2_base(reg, ks, repo, base, branch, emit_cosign=True)
    _run("run_merge_gate.py", "--repo-dir", str(repo), "--registry-dir", str(reg),
         "--bus-id", "prod", "--main-ref", "refs/threeway/test-main", "--run-once",
         repo=repo, ks=ks)
    assert _git(repo, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ
    state = verify_and_reduce(RefEventStore(repo).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.merge_completed(cid) is not None


def test_t2_missing_cosign_stays_pending(seatkit, live_repo):
    reg, ks, privs = seatkit
    repo, base, branch = live_repo
    cid, integ = _emit_t2_base(reg, ks, repo, base, branch, emit_cosign=False)
    _run("run_merge_gate.py", "--repo-dir", str(repo), "--registry-dir", str(reg),
         "--bus-id", "prod", "--main-ref", "refs/threeway/test-main", "--run-once",
         repo=repo, ks=ks)
    state = verify_and_reduce(RefEventStore(repo).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.merge_completed(cid) is None
    assert _git(repo, "rev-parse", "refs/threeway/test-main").stdout.strip() == base


def test_t2_forged_wrong_seat_cosign_does_not_satisfy_gate(seatkit, live_repo):
    reg, ks, privs = seatkit
    repo, base, branch = live_repo
    cid, integ = _emit_t2_base(reg, ks, repo, base, branch, emit_cosign=False)
    bad = Event(id="co_sign-operator-forged", seq=0, bus_id="prod", schema_version="threeway/1",
                kind="co_sign", sender="operator", recipient="all",
                signer="operator:claude:forged", payload={"verdict": "GO"},
                candidate_id=cid, subject_sha=integ, brief_id="b1", brief_version=1)
    RefEventStore(repo).append(bad, keys.load_private("operator"))
    _run("run_merge_gate.py", "--repo-dir", str(repo), "--registry-dir", str(reg),
         "--bus-id", "prod", "--main-ref", "refs/threeway/test-main", "--run-once",
         repo=repo, ks=ks)
    state = verify_and_reduce(RefEventStore(repo).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.merge_completed(cid) is None
    assert _git(repo, "rev-parse", "refs/threeway/test-main").stdout.strip() == base


def _emit_t3_extras(reg, ks, repo, cid, integ, *, approvals=("chief-gemini", "chief-chatgpt")):
    L = ["--repo-dir", str(repo), "--remote", ""]
    _run("overseer_emit.py", "approver_roster", "--candidate-id", cid,
         "--approvers", "chief-gemini", "chief-chatgpt", *L, repo=repo, ks=ks)
    _run("overseer_emit.py", "re_verify_challenge", "--candidate-id", cid,
         "--integration-sha", integ, "--nonce", "fresh-nonce", *L, repo=repo, ks=ks)
    _run("seat_emit.py", "operator", "re_verify", "--candidate-id", cid,
         "--registry-dir", str(reg), *L, repo=repo, ks=ks)
    for approver in approvals:
        _run("chief_emit.py", approver, "human_approval", "--candidate-id", cid,
             "--integration-sha", integ, "--registry-dir", str(reg), *L, repo=repo, ks=ks)


def test_t3_cli_happy_path_merges_with_reverify_and_two_chiefs(seatkit, live_repo):
    reg, ks, privs = seatkit
    repo, base, branch = live_repo
    cid, integ = _emit_t2_base(reg, ks, repo, base, branch, emit_cosign=True, tier="T3")
    _emit_t3_extras(reg, ks, repo, cid, integ)
    _run("run_merge_gate.py", "--repo-dir", str(repo), "--registry-dir", str(reg),
         "--bus-id", "prod", "--main-ref", "refs/threeway/test-main", "--run-once",
         repo=repo, ks=ks)
    state = verify_and_reduce(RefEventStore(repo).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.merge_completed(cid) is not None


def test_t3_one_human_approval_stays_pending(seatkit, live_repo):
    reg, ks, privs = seatkit
    repo, base, branch = live_repo
    cid, integ = _emit_t2_base(reg, ks, repo, base, branch, emit_cosign=True, tier="T3")
    _emit_t3_extras(reg, ks, repo, cid, integ, approvals=("chief-gemini",))
    _run("run_merge_gate.py", "--repo-dir", str(repo), "--registry-dir", str(reg),
         "--bus-id", "prod", "--main-ref", "refs/threeway/test-main", "--run-once",
         repo=repo, ks=ks)
    state = verify_and_reduce(RefEventStore(repo).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.merge_completed(cid) is None
    assert _git(repo, "rev-parse", "refs/threeway/test-main").stdout.strip() == base


def test_t3_revoking_cosign_makes_unmerged_candidate_pending(seatkit, live_repo):
    reg, ks, privs = seatkit
    repo, base, branch = live_repo
    cid, integ = _emit_t2_base(reg, ks, repo, base, branch, emit_cosign=True, tier="T3")
    target = [e for e in RefEventStore(repo).all_events() if e.kind == "co_sign"][-1]
    _run("seat_emit.py", "operator2", "attestation_revoked", "--candidate-id", cid,
         "--revokes-event-id", target.id, "--repo-dir", str(repo), "--remote", "",
         repo=repo, ks=ks)
    _emit_t3_extras(reg, ks, repo, cid, integ)
    _run("run_merge_gate.py", "--repo-dir", str(repo), "--registry-dir", str(reg),
         "--bus-id", "prod", "--main-ref", "refs/threeway/test-main", "--run-once",
         repo=repo, ks=ks)
    state = verify_and_reduce(RefEventStore(repo).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.merge_completed(cid) is None
    assert _git(repo, "rev-parse", "refs/threeway/test-main").stdout.strip() == base
