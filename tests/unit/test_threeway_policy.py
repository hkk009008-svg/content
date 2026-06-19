"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_policy.py -q"""
from threeway.policy import default_policy


def test_policy_digest_is_stable_and_hex():
    p = default_policy()
    d = p.policy_digest()
    assert isinstance(d, str) and len(d) == 64
    assert default_policy().policy_digest() == d  # deterministic


def test_current_policy_is_accepted():
    p = default_policy()
    assert p.is_accepted(p.policy_digest())
    assert not p.is_accepted("deadbeef")


def test_required_ci_present_for_every_tier():
    p = default_policy()
    for tier in ("T0", "T1", "T2", "T3"):
        assert p.required_ci(tier)
