"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_tier.py -q"""
from threeway.policy import default_policy
from threeway.tier import classify_diff, effective_tier, co_sign_satisfied, tier_rank
from threeway.reducer import reduce


P = default_policy()


def test_docs_only_is_t0():
    # both under docs/ — root-level docs (README.md etc.) intentionally fall to the
    # T1 default, which is SAFE (over-classify never under-promotes); see
    # _DEFAULT_RULES in threeway/policy.py.
    assert classify_diff(["docs/x.md", "docs/guide.md"], P) == "T0"


def test_bounded_code_is_t1():
    assert classify_diff(["cinema/foo.py"], P) == "T1"


def test_ci_config_is_t2():
    assert classify_diff([".github/workflows/ci.yml"], P) == "T2"


def test_keys_dir_is_t3():
    assert classify_diff(["coordination/threeway/keys/operator.pub"], P) == "T3"


def test_classify_takes_the_max_over_all_paths():
    assert classify_diff(["docs/x.md", ".github/workflows/ci.yml"], P) == "T2"


def test_effective_tier_is_max_of_claimed_and_path_derived():
    # path-derived T1, brief claimed T2 -> T2
    assert effective_tier("T2", ["cinema/foo.py"], P) == "T2"
    # path-derived T2, brief claimed T0 -> T2 (claim never lowers it)
    assert effective_tier("T0", [".github/workflows/ci.yml"], P) == "T2"


def test_t0_t1_cosign_satisfied_without_extra_artifacts():
    state = reduce([])
    assert co_sign_satisfied("T0", state, candidate_id="c1", builder_provider="codex")
    assert co_sign_satisfied("T1", state, candidate_id="c1", builder_provider="codex")


def test_t2_t3_not_satisfiable_in_slice1():
    state = reduce([])
    assert not co_sign_satisfied("T2", state, candidate_id="c1", builder_provider="codex")
    assert not co_sign_satisfied("T3", state, candidate_id="c1", builder_provider="codex")
