"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_loop.py -q"""
from threeway import keys
from threeway.loop import build_candidate_events
from threeway.policy import default_policy


def test_build_candidate_events_has_all_required_kinds():
    privs = {s: keys.generate_keypair()[0] for s in
             ("director", "operator", "coordinator", "overseer", "ci")}
    events = build_candidate_events("1" * 40, "3" * 40, "2" * 40, privs)
    kinds = {e.kind for e in events}
    assert {"brief", "assignment", "candidate", "attestation", "cycle_go",
            "ci_result", "release_requested", "release_order"} <= kinds
    # two attestations: preliminary + release
    atts = [e for e in events if e.kind == "attestation"]
    assert {a.payload["kind"] for a in atts} == {"preliminary", "release"}


def test_build_candidate_events_uses_accepted_policy_digest():
    privs = {s: keys.generate_keypair()[0] for s in
             ("director", "operator", "coordinator", "overseer", "ci")}
    events = build_candidate_events("1" * 40, "3" * 40, "2" * 40, privs)
    pd = default_policy().policy_digest()
    cand = next(e for e in events if e.kind == "candidate")
    assert cand.payload["policy_digest"] == pd
