"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_chief_emit.py -q"""

import contextlib
import io

from threeway.gate import verify_and_reduce
from threeway.refstore import RefEventStore
from tests.unit.test_threeway_overseer_emit import _new_repo, seatkit


def _run(argv):
    from scripts.chief_emit import main
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


def test_rostered_chief_human_approval_round_trips(seatkit, tmp_path):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts.overseer_emit import main as omain
    common = ["--candidate-id", "A:c1", "--repo-dir", str(repo), "--remote", ""]
    assert omain(["approver_roster", "--approvers", "chief-gemini", "chief-chatgpt", *common]) == 0
    rc, _, err = _run(["chief-gemini", "human_approval", "--candidate-id", "A:c1",
                       "--integration-sha", "1" * 40, "--registry-dir", str(reg),
                       "--repo-dir", str(repo), "--remote", ""])
    assert rc == 0, err
    state = verify_and_reduce(RefEventStore(repo).all_events(), registry_dir=str(reg), bus_id="prod")
    approvals = state.human_approvals("A:c1")
    assert len(approvals) == 1
    assert approvals[0].signer.split(":", 1)[0] == "chief-gemini"
    assert approvals[0].payload["decision"] == "approve"


def test_unrostered_chief_is_rc2_zero_events(seatkit, tmp_path):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts.overseer_emit import main as omain
    assert omain(["approver_roster", "--candidate-id", "A:c1",
                  "--approvers", "chief-chatgpt", "--repo-dir", str(repo), "--remote", ""]) == 0
    n0 = len(RefEventStore(repo).all_events())
    rc, _, err = _run(["chief-gemini", "human_approval", "--candidate-id", "A:c1",
                       "--integration-sha", "1" * 40, "--registry-dir", str(reg),
                       "--repo-dir", str(repo), "--remote", ""])
    assert rc == 2
    assert "not rostered" in err
    assert len(RefEventStore(repo).all_events()) == n0


def test_chief_can_revoke_own_approval(seatkit, tmp_path):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts.overseer_emit import main as omain
    assert omain(["approver_roster", "--candidate-id", "A:c1",
                  "--approvers", "chief-gemini", "chief-chatgpt",
                  "--repo-dir", str(repo), "--remote", ""]) == 0
    assert _run(["chief-gemini", "human_approval", "--candidate-id", "A:c1",
                 "--integration-sha", "1" * 40, "--registry-dir", str(reg),
                 "--repo-dir", str(repo), "--remote", ""])[0] == 0
    target = [e for e in RefEventStore(repo).all_events() if e.kind == "human_approval"][-1]
    rc, _, err = _run(["chief-gemini", "attestation_revoked", "--candidate-id", "A:c1",
                       "--revokes-event-id", target.id, "--registry-dir", str(reg),
                       "--repo-dir", str(repo), "--remote", ""])
    assert rc == 0, err
    state = verify_and_reduce(RefEventStore(repo).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.human_approvals("A:c1") == []
